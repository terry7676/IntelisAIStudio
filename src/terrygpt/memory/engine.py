from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from typing import Any

from terrygpt.core.module import BaseModule, ModuleHealth
from terrygpt.database.manager import DatabaseManager, new_id, utc_now
from terrygpt.memory.models import MemoryItem, MemorySearchResult


TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


class MemoryEngine(BaseModule):
    def __init__(self) -> None:
        super().__init__(name="memory_engine", dependencies=("database",))
        self.database: DatabaseManager | None = None

    def on_initialize(self) -> None:
        self.database = self._database()
        if self.context is not None:
            self.context.event_bus.subscribe("memory.remember.requested", self._handle_remember_event)

    def remember(
        self,
        memory_type: str,
        content: str,
        importance: int = 50,
        expires_at: str | None = None,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryItem:
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Memory content cannot be empty.")
        clamped_importance = max(0, min(100, importance))
        memory_id = new_id()
        timestamp = utc_now()
        final_summary = summary.strip() if summary else self.summarize(clean_content)
        metadata_json = json.dumps(metadata or {}, sort_keys=True)

        database = self._database()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO memory
                    (id, memory_type, content, summary, importance, expires_at, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    memory_type,
                    clean_content,
                    final_summary,
                    clamped_importance,
                    expires_at,
                    metadata_json,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute("INSERT INTO memory_search (content, memory_id) VALUES (?, ?)", (clean_content, memory_id))

        item = MemoryItem(
            id=memory_id,
            memory_type=memory_type,
            content=clean_content,
            summary=final_summary,
            importance=clamped_importance,
            expires_at=expires_at,
            metadata_json=metadata_json,
            created_at=timestamp,
            updated_at=timestamp,
        )
        if self.context is not None:
            self.context.event_bus.publish("memory.created", {"id": memory_id, "type": memory_type}, source=self.name)
        return item

    def search(self, query: str, limit: int = 20, include_expired: bool = False) -> list[MemorySearchResult]:
        clean_query = query.strip()
        if not clean_query:
            return []
        rows = self._search_rows(clean_query, limit * 3, include_expired)
        query_tokens = self._tokens(clean_query)
        results: list[MemorySearchResult] = []
        for row in rows:
            item = MemoryItem(
                id=str(row["id"]),
                memory_type=str(row["memory_type"]),
                content=str(row["content"]),
                summary=str(row["summary"]),
                importance=int(row["importance"]),
                expires_at=row["expires_at"],
                metadata_json=str(row["metadata_json"]),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            score = self._score(item, query_tokens)
            results.append(MemorySearchResult(item=item, score=score))

        results.sort(key=lambda result: result.score, reverse=True)
        return results[:limit]

    def summarize(self, content: str, max_chars: int = 240) -> str:
        normalized = " ".join(content.split())
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 3].rstrip() + "..."

    def expire_due_memories(self) -> int:
        now = datetime.now(UTC).isoformat()
        rows = self._database().fetch_all("SELECT id FROM memory WHERE expires_at IS NOT NULL AND expires_at <= ?", (now,))
        return len(rows)

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=self.database is not None,
            detail="Long-term memory storage ready",
        )

    def _database(self) -> DatabaseManager:
        if self.database is not None:
            return self.database
        if self.context is None:
            raise RuntimeError("MemoryEngine has no CoreContext.")
        from terrygpt.core.manager import CoreManager

        core = getattr(self.context, "core", None)
        if isinstance(core, CoreManager):
            database = core.module("database")
        else:
            raise RuntimeError("MemoryEngine requires CoreManager access to database.")
        if not isinstance(database, DatabaseManager):
            raise RuntimeError("Registered database module is invalid.")
        self.database = database
        return database

    def _handle_remember_event(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        self.remember(
            memory_type=str(payload.get("memory_type", "event")),
            content=str(payload.get("content", "")),
            importance=int(payload.get("importance", 50)),
            metadata=dict(payload.get("metadata", {})),
        )

    def _search_rows(self, query: str, limit: int, include_expired: bool):
        database = self._database()
        now = datetime.now(UTC).isoformat()
        expiration_clause = "" if include_expired else "AND (m.expires_at IS NULL OR m.expires_at > ?)"
        expiration_parameters: tuple[object, ...] = () if include_expired else (now,)
        with database.connect() as connection:
            try:
                return connection.execute(
                    f"""
                    SELECT m.*
                    FROM memory_search s
                    JOIN memory m ON m.id = s.memory_id
                    WHERE memory_search MATCH ? {expiration_clause}
                    LIMIT ?
                    """,
                    (query, *expiration_parameters, limit),
                ).fetchall()
            except Exception:
                return connection.execute(
                    f"""
                    SELECT m.*
                    FROM memory m
                    WHERE m.content LIKE ? {expiration_clause}
                    ORDER BY m.updated_at DESC
                    LIMIT ?
                    """,
                    (f"%{query}%", *expiration_parameters, limit),
                ).fetchall()

    def _score(self, item: MemoryItem, query_tokens: set[str]) -> float:
        content_tokens = self._tokens(item.content)
        overlap = len(query_tokens & content_tokens)
        token_score = overlap / max(1, len(query_tokens))
        importance_score = item.importance / 100
        created = datetime.fromisoformat(item.created_at)
        age_days = max(0.0, (datetime.now(UTC) - created).total_seconds() / 86_400)
        recency_score = 1 / (1 + math.log1p(age_days))
        return (token_score * 0.55) + (importance_score * 0.30) + (recency_score * 0.15)

    def _tokens(self, text: str) -> set[str]:
        return {token.lower() for token in TOKEN_RE.findall(text)}

