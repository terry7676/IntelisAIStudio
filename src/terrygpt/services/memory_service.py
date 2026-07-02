from __future__ import annotations

import json
from typing import Any

from terrygpt.database import TerryDatabase
from terrygpt.models import MemoryRecord


class MemoryService:
    def __init__(self, database: TerryDatabase) -> None:
        self.database = database

    def remember(self, kind: str, content: str, metadata: dict[str, Any] | None = None) -> MemoryRecord:
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Memory content cannot be empty.")
        metadata_json = json.dumps(metadata or {}, sort_keys=True)
        return self.database.add_memory(kind=kind, content=clean_content, metadata_json=metadata_json)

    def search(self, query: str, limit: int = 20) -> list[MemoryRecord]:
        return self.database.search_memories(query=query, limit=limit)

