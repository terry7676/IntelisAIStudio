from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from terrygpt.core.module import BaseModule, ModuleHealth


@dataclass(frozen=True)
class ProviderHealth:
    name: str
    available: bool
    detail: str


@dataclass(frozen=True)
class ProviderMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ProviderChunk:
    content: str
    done: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_duration_ms: int = 0


@dataclass(frozen=True)
class ProviderModelInfo:
    provider_name: str
    model_name: str
    parameter_size: str
    size_bytes: int
    quantization: str
    context_length: int
    metadata: dict[str, Any]


class AIProvider(Protocol):
    name: str

    def health(self) -> ProviderHealth:
        raise NotImplementedError

    def list_models(self) -> list[str]:
        raise NotImplementedError

    def model_details(self) -> list[ProviderModelInfo]:
        raise NotImplementedError

    def stream_chat(
        self,
        model: str,
        messages: list[ProviderMessage],
        options: dict[str, Any],
    ):
        raise NotImplementedError


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, timeout_seconds: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def health(self) -> ProviderHealth:
        try:
            models = self.list_models()
        except Exception as exc:
            return ProviderHealth(self.name, False, str(exc))
        return ProviderHealth(self.name, True, f"{len(models)} model(s) reported")

    def list_models(self) -> list[str]:
        data = self._json_get("/api/tags")
        raw_models = data.get("models", [])
        if not isinstance(raw_models, list):
            return []
        return [item["name"] for item in raw_models if isinstance(item, dict) and isinstance(item.get("name"), str)]

    def model_details(self) -> list[ProviderModelInfo]:
        data = self._json_get("/api/tags")
        raw_models = data.get("models", [])
        if not isinstance(raw_models, list):
            return []
        models: list[ProviderModelInfo] = []
        for item in raw_models:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            name = item["name"]
            details = item.get("details", {})
            if not isinstance(details, dict):
                details = {}
            show_data = self._json_post_optional("/api/show", {"model": name})
            model_info = show_data.get("model_info", {}) if isinstance(show_data, dict) else {}
            if not isinstance(model_info, dict):
                model_info = {}
            context_length = self._extract_context_length(model_info)
            models.append(
                ProviderModelInfo(
                    provider_name=self.name,
                    model_name=name,
                    parameter_size=str(details.get("parameter_size", "")),
                    size_bytes=int(item.get("size", 0) or 0),
                    quantization=str(details.get("quantization_level", "")),
                    context_length=context_length,
                    metadata={"tags": item, "show": show_data},
                )
            )
        return models

    def stream_chat(
        self,
        model: str,
        messages: list[ProviderMessage],
        options: dict[str, Any],
    ):
        payload = {
            "model": model,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "stream": True,
            "options": options,
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
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
                    data = json.loads(line)
                    if isinstance(data.get("error"), str):
                        raise RuntimeError(data["error"])
                    message = data.get("message", {})
                    content = message.get("content", "") if isinstance(message, dict) else ""
                    yield ProviderChunk(
                        content=str(content),
                        done=bool(data.get("done", False)),
                        prompt_tokens=int(data.get("prompt_eval_count", 0) or 0),
                        completion_tokens=int(data.get("eval_count", 0) or 0),
                        total_duration_ms=int((data.get("total_duration", 0) or 0) / 1_000_000),
                    )
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama stream failed at {self.base_url}") from exc

    def _json_get(self, path: str) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.base_url}{path}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ollama not available at {self.base_url}") from exc

    def _json_post_optional(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return {}

    def _extract_context_length(self, model_info: dict[str, Any]) -> int:
        for key, value in model_info.items():
            if key.endswith(".context_length") or key.endswith(".max_position_embeddings"):
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return 0
        return 0


class AIProviderRegistry(BaseModule):
    def __init__(self) -> None:
        super().__init__(name="ai_provider_registry")
        self._providers: dict[str, AIProvider] = {}
        self._last_health: dict[str, ProviderHealth] = {}

    def register_provider(self, provider: AIProvider) -> None:
        self._providers[provider.name] = provider

    def on_initialize(self) -> None:
        self.refresh_health()

    def refresh_health(self) -> dict[str, ProviderHealth]:
        self._last_health = {name: provider.health() for name, provider in self._providers.items()}
        if self.context is not None:
            self.context.event_bus.publish(
                "ai.providers.checked",
                {"providers": {name: health.__dict__ for name, health in self._last_health.items()}},
                source=self.name,
            )
        return self._last_health

    def list_providers(self) -> list[str]:
        return sorted(self._providers)

    def provider(self, name: str) -> AIProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"Unknown AI provider: {name}") from exc

    def provider_health(self) -> dict[str, ProviderHealth]:
        return dict(self._last_health)

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=True,
            detail=f"{len(self._providers)} provider(s) registered",
        )
