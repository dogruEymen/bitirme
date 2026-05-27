from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import json
import httpx
from datetime import datetime

from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.ollama_service import get_ollama_service
from backend.app.core.database import get_db, SessionLocal
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
        title = first_msg.content[:40] + "..." if first_msg else "New Chat"
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
            "created_at": datetime.utcnow().isoformat()
        }
        for m in messages
    ]


@router.post("/chat/sessions/{session_id}/message")
async def send_message_stream(session_id: int, msg: ChatRequest, request: Request, db: Session = Depends(get_db)):
    user_id = get_user_id_from_request(request, db)
    get_user_chat_session(session_id, user_id, db)

    # 1. Save user message to database
    user_msg = ChatMessage(chat_id=session_id, role="user", content=msg.message)
    db.add(user_msg)
    db.commit()
    
    # 2. Get chat history to build context prompt for Ollama
    history = db.query(ChatMessage).filter(ChatMessage.chat_id == session_id).order_by(ChatMessage.id.asc()).limit(20).all()
    
    # Build prompt
    prompt_lines = []
    prompt_lines.append("You are a helpful, professional Academic Research Assistant. You assist researchers in finding information, analyzing topics, and understanding cluster data.")
    for h in history:
        role = "User" if h.role == "user" else "Assistant"
        prompt_lines.append(f"{role}: {h.content}")
        
    prompt_lines.append("Assistant:")
    prompt = "\n".join(prompt_lines)
    
    # Get ollama service config
    service = get_ollama_service()
    
    async def event_generator():
        url = f"{service.base_url}/api/generate"
        payload = {
            "model": service.model,
            "prompt": prompt,
            "stream": True,
        }
        full_response = ""
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        yield f"Error: Ollama API returned status {response.status_code}"
                        return
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                chunk = data.get("response", "")
                                full_response += chunk
                                yield chunk
                            except Exception:
                                pass
        except Exception as e:
            yield f"Error: Failed to stream response from Ollama: {str(e)}"
            return
            
        # Save assistant message to DB
        if full_response.strip():
            db_write = SessionLocal()
            try:
                agent_msg = ChatMessage(chat_id=session_id, role="agent", content=full_response.strip())
                db_write.add(agent_msg)
                db_write.commit()
            except Exception as e:
                db_write.rollback()
                print(f"Error saving assistant response: {e}")
            finally:
                db_write.close()

    return StreamingResponse(event_generator(), media_type="text/plain")


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
