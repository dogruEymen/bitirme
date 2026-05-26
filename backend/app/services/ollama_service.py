import json
from functools import lru_cache

import requests

from backend.app.core.config import settings


class OllamaServiceError(RuntimeError):
    pass


class OllamaService:
    def __init__(self, base_url: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL

    def generate(self, prompt: str) -> str:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
        }

        try:
            response = requests.post(url, json=payload, stream=True, timeout=120)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaServiceError("Ollama servisine ulasilamadi veya yanit alinamadi.") from exc

        chunks: list[str] = []
        try:
            for line in response.iter_lines():
                if not line:
                    continue

                data = json.loads(line.decode("utf-8"))
                chunks.append(data.get("response", ""))

                if data.get("done"):
                    break
        except json.JSONDecodeError as exc:
            raise OllamaServiceError("Ollama gecersiz JSON yaniti dondu.") from exc

        return "".join(chunks).strip()


@lru_cache(maxsize=1)
def get_ollama_service() -> OllamaService:
    return OllamaService()
