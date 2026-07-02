from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Conversation:
    id: str
    title: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ChatMessage:
    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str


@dataclass(frozen=True)
class MemoryRecord:
    id: str
    kind: str
    content: str
    metadata_json: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class PluginInfo:
    name: str
    version: str
    description: str
    commands: tuple[str, ...]

