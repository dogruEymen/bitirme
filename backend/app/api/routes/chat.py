from fastapi import APIRouter

from backend.app.schemas.chat import ChatRequest, ChatResponse
from backend.app.services.ollama_service import generate_response


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(msg: ChatRequest):
    answer = await generate_response(msg.message)
    return ChatResponse(modelResponse=answer)
