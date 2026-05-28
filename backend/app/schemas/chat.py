from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    modelResponse: str


class ChatMessageResponse(BaseModel):
    id: str
    role: str
    content: str
    created_at: str
    metadata_json: dict | None = None
