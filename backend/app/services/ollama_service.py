import json
from functools import lru_cache
from collections.abc import AsyncIterator

import httpx
import requests

from backend.app.core.config import settings


class OllamaServiceError(RuntimeError):
    pass


class OllamaService:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.MODEL_NAME

    def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.RequestException as exc:
            raise OllamaServiceError("Ollama servisine ulasilamadi veya yanit alinamadi.") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise OllamaServiceError("Ollama gecersiz JSON yaniti dondu.") from exc

    async def generate_async(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                return data.get("response", "").strip()
        except httpx.HTTPError as exc:
            raise OllamaServiceError("Ollama servisine ulasilamadi veya yanit alinamadi.") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise OllamaServiceError("Ollama gecersiz JSON yaniti dondu.") from exc

    async def stream_generate(self, prompt: str) -> AsyncIterator[str]:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
        }

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        data = json.loads(line)
                        chunk = data.get("response", "")
                        if chunk:
                            yield chunk
        except httpx.HTTPError as exc:
            raise OllamaServiceError("Ollama servisine ulasilamadi veya yanit alinamadi.") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise OllamaServiceError("Ollama gecersiz JSON yaniti dondu.") from exc


@lru_cache(maxsize=1)
def get_ollama_service() -> OllamaService:
    return OllamaService()
