from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Iterable

from terrygpt.models import ChatMessage


class OllamaError(RuntimeError):
    """Raised when TerryGPT cannot complete an Ollama request."""


@dataclass(frozen=True)
class OllamaModel:
    name: str


class OllamaClient:
    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _json_request(self, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self._url(path),
            data=body,
            headers={"Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OllamaError(f"Could not reach Ollama at {self.base_url}.") from exc
        except json.JSONDecodeError as exc:
            raise OllamaError("Ollama returned invalid JSON.") from exc

    def list_models(self) -> list[OllamaModel]:
        data = self._json_request("/api/tags")
        raw_models = data.get("models", [])
        if not isinstance(raw_models, list):
            return []
        models: list[OllamaModel] = []
        for item in raw_models:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                models.append(OllamaModel(name=item["name"]))
        return models

    def stream_chat(self, model: str, messages: Iterable[ChatMessage]) -> Iterable[str]:
        if not model.strip():
            raise OllamaError("No Ollama model is configured or installed.")

        payload = {
            "model": model,
            "stream": True,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
                if message.role in {"system", "user", "assistant"}
            ],
        }
        request = urllib.request.Request(
            self._url("/api/chat"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise OllamaError("Ollama returned an invalid streaming message.") from exc

                    if isinstance(data.get("error"), str):
                        raise OllamaError(data["error"])

                    message = data.get("message", {})
                    if isinstance(message, dict) and isinstance(message.get("content"), str):
                        chunk = message["content"]
                        if chunk:
                            yield chunk

                    if data.get("done") is True:
                        break
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise OllamaError(f"Could not reach Ollama at {self.base_url}.") from exc

