import json
from functools import lru_cache

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


@lru_cache(maxsize=1)
def get_ollama_service() -> OllamaService:
    return OllamaService()
