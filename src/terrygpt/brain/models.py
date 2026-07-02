from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from terrygpt.ai.providers import ProviderMessage


class ConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


@dataclass(frozen=True)
class ConversationRecord:
    id: str
    title: str
    status: ConversationStatus
    created_at: str
    updated_at: str
    archived_at: str | None = None
    summary: str = ""
    model_name: str = ""
    provider_name: str = ""


@dataclass(frozen=True)
class MessageRecord:
    id: str
    conversation_id: str
    role: str
    content: str
    token_count: int
    metadata: dict[str, Any]
    created_at: str


@dataclass(frozen=True)
class ModelInfo:
    provider_name: str
    model_name: str
    parameter_size: str
    size_bytes: int
    quantization: str
    context_length: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def display_size(self) -> str:
        if self.size_bytes <= 0:
            return "Unknown"
        gb = self.size_bytes / 1024 / 1024 / 1024
        return f"{gb:.2f} GB"


@dataclass(frozen=True)
class BrainSettings:
    provider_name: str = "ollama"
    default_model: str = ""
    temperature: float = 0.7
    top_p: float = 0.9
    maximum_tokens: int = 2048
    streaming_enabled: bool = True
    memory_enabled: bool = True
    system_prompt: str = "You are TerryGPT, a local-first assistant running on Terry's Windows PC."


@dataclass(frozen=True)
class PromptTemplate:
    id: str
    name: str
    prompt_type: str
    version: int
    template: str
    variables: tuple[str, ...]
    active: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class BuiltContext:
    messages: list[ProviderMessage]
    memory_ids: tuple[str, ...]
    prompt_tokens_estimate: int
    system_prompt: str


@dataclass(frozen=True)
class ResponseChunk:
    content: str
    done: bool = False
    conversation_id: str = ""
    request_id: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    response_time_ms: int = 0
    error: str = ""

