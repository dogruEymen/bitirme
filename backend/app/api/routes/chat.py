from fastapi import APIRouter, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.ollama_service import OllamaServiceError, get_ollama_service


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(msg: ChatRequest):
    service = get_ollama_service()
    try:
        answer = await run_in_threadpool(service.generate, msg.message)
    except OllamaServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    return ChatResponse(modelResponse=answer)
