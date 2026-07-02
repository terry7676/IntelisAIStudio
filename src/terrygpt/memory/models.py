from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryItem:
    id: str
    memory_type: str
    content: str
    summary: str
    importance: int
    expires_at: str | None
    metadata_json: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class MemorySearchResult:
    item: MemoryItem
    score: float

