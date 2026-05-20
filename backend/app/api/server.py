from pydantic import BaseModel
from fastapi import FastAPI
import httpx
import json

class ChatRequest(BaseModel):
    message: str
class ChatResponse(BaseModel):
    modelResponse: str

app = FastAPI()

# API endpoint
@app.post("/chat", response_model=ChatResponse)
async def chat(msg: ChatRequest):
    # mock_answer = "coming soon ..."
    answer = await aiClient(msg)
    return { "modelResponse" : answer }

# Client for AI Server
async def aiClient(msg: ChatRequest):
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            "http://localhost:11434/api/generate",
            json={"model": "gemma4", "prompt": msg.message}
        )
        result_text = ""
        # line-delimited JSON parsing
        for line in response.text.splitlines():
            if line.strip():  # boş satırları atla
                obj = json.loads(line)
                result_text += obj.get("response", "")
        return result_text

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
