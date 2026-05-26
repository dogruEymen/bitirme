import json

import httpx

from backend.app.core.config import settings


async def generate_response(prompt: str) -> str:
    async with httpx.AsyncClient(timeout=100.0) as client:
        response = await client.post(
            f"{settings.OLLAMA_BASE_URL}/api/generate",
            json={"model": settings.OLLAMA_MODEL, "prompt": prompt},
        )
        response.raise_for_status()

    result_text = ""
    for line in response.text.splitlines():
        if line.strip():
            obj = json.loads(line)
            result_text += obj.get("response", "")

    return result_text
