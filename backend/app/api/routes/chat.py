from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime

from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.ollama_service import get_ollama_service
from backend.app.services.chat_orchestrator import get_chat_orchestrator
from backend.app.core.database import get_db
from database.models.ChatMessage import ChatMessage
from database.models.ChatSession import ChatSession
from database.models.User import User

router = APIRouter()


def hash_to_int(value: str) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def get_or_create_default_user(db: Session) -> int:
    user = db.query(User).filter(User.username == "default_user").first()
    if not user:
        user = User(username="default_user", email="default@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user.id


def get_user_id_from_request(request: Request, db: Session) -> int:
    header_user = request.headers.get("X-User-Id")
    if header_user:
        user_id = hash_to_int(header_user)
        if user_id is not None:
            user = db.query(User).filter(User.id == user_id).first()
            if user:
                return user.id
    return get_or_create_default_user(db)


def get_user_chat_session(session_id: int, user_id: int, db: Session) -> ChatSession:
    session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == user_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found.")
    return session


@router.get("/chat/sessions")
def get_sessions(request: Request, db: Session = Depends(get_db)):
    user_id = get_user_id_from_request(request, db)
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).order_by(ChatSession.id.desc()).all()
    
    result = []
    for s in sessions:
        first_msg = db.query(ChatMessage).filter(ChatMessage.chat_id == s.id).order_by(ChatMessage.id.asc()).first()
        title = s.title or (first_msg.content[:40] + "..." if first_msg else "New Chat")
        result.append({
            "id": str(s.id),
            "title": title
        })
    return result


@router.post("/chat/sessions")
def create_session(request: Request, db: Session = Depends(get_db)):
    user_id = get_user_id_from_request(request, db)
    session = ChatSession(user_id=user_id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return {"id": str(session.id), "title": "New Chat"}


@router.delete("/chat/sessions/{session_id}")
def delete_session(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_user_id_from_request(request, db)
    session = get_user_chat_session(session_id, user_id, db)

    db.query(ChatMessage).filter(ChatMessage.chat_id == session.id).delete()
    db.delete(session)
    db.commit()
    return {"success": True}


@router.get("/chat/sessions/{session_id}/messages")
def get_messages(session_id: int, request: Request, db: Session = Depends(get_db)):
    user_id = get_user_id_from_request(request, db)
    get_user_chat_session(session_id, user_id, db)

    messages = db.query(ChatMessage).filter(ChatMessage.chat_id == session_id).order_by(ChatMessage.id.asc()).all()
    return [
        {
            "id": str(m.id),
            "role": "assistant" if m.role == "agent" else "user",
            "content": m.content,
            "created_at": (m.created_at or datetime.utcnow()).isoformat(),
            "metadata_json": m.metadata_json,
        }
        for m in messages
    ]


@router.post("/chat/sessions/{session_id}/message")
async def send_message_stream(session_id: int, msg: ChatRequest, request: Request, db: Session = Depends(get_db)):
    user_id = get_user_id_from_request(request, db)
    get_user_chat_session(session_id, user_id, db)
    orchestrator = get_chat_orchestrator()
    return StreamingResponse(
        orchestrator.stream_session_message(session_id, user_id, msg.message),
        media_type="text/plain",
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(msg: ChatRequest):
    """Keep the old endpoint for backward compatibility / fallback"""
    service = get_ollama_service()
    try:
        # Simply run the generate method inside a threadpool since requests is synchronous
        from fastapi.concurrency import run_in_threadpool
        answer = await run_in_threadpool(service.generate, msg.message)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatResponse(modelResponse=answer)
