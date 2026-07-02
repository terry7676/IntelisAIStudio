from __future__ import annotations

import json
from pathlib import Path

from terrygpt.database.manager import DatabaseManager, new_id, utc_now
from terrygpt.models import ChatMessage, Conversation, MemoryRecord


class TerryDatabase:
    """Backward-compatible repository used by Phase 1 tests and services."""

    def __init__(self, path: Path) -> None:
        self.manager = DatabaseManager(path)

    @property
    def path(self) -> Path:
        return self.manager.database_path

    def connect(self):
        return self.manager.connect()

    def initialize(self) -> None:
        self.manager.migrate()

    def create_conversation(self, title: str) -> Conversation:
        timestamp = utc_now()
        conversation = Conversation(id=new_id(), title=title, created_at=timestamp, updated_at=timestamp)
        with self.manager.connect() as connection:
            connection.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation.id, conversation.title, conversation.created_at, conversation.updated_at),
            )
        return conversation

    def list_conversations(self) -> list[Conversation]:
        rows = self.manager.fetch_all(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        )
        return [Conversation(**dict(row)) for row in rows]

    def add_message(self, conversation_id: str, role: str, content: str) -> ChatMessage:
        timestamp = utc_now()
        message = ChatMessage(new_id(), conversation_id, role, content, timestamp)
        with self.manager.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (message.id, message.conversation_id, message.role, message.content, message.created_at),
            )
            connection.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (timestamp, conversation_id))
        return message

    def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        rows = self.manager.fetch_all(
            """
            SELECT id, conversation_id, role, content, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
            """,
            (conversation_id,),
        )
        return [ChatMessage(**dict(row)) for row in rows]

    def add_memory(self, kind: str, content: str, metadata_json: str = "{}") -> MemoryRecord:
        timestamp = utc_now()
        memory = MemoryRecord(new_id(), kind, content, metadata_json, timestamp, timestamp)
        with self.manager.connect() as connection:
            connection.execute(
                """
                INSERT INTO memory (id, memory_type, content, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory.id, memory.kind, memory.content, memory.metadata_json, memory.created_at, memory.updated_at),
            )
            connection.execute("INSERT INTO memory_search (content, memory_id) VALUES (?, ?)", (content, memory.id))
        return memory

    def search_memories(self, query: str, limit: int = 20) -> list[MemoryRecord]:
        clean_query = query.strip()
        if not clean_query:
            return []
        with self.manager.connect() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT m.id, m.memory_type AS kind, m.content, m.metadata_json, m.created_at, m.updated_at
                    FROM memory_search s
                    JOIN memory m ON m.id = s.memory_id
                    WHERE memory_search MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (clean_query, limit),
                ).fetchall()
            except Exception:
                rows = connection.execute(
                    """
                    SELECT id, memory_type AS kind, content, metadata_json, created_at, updated_at
                    FROM memory
                    WHERE content LIKE ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (f"%{clean_query}%", limit),
                ).fetchall()
        return [MemoryRecord(**dict(row)) for row in rows]

    def add_audit_log(self, event_type: str, detail: str) -> None:
        self.manager.add_audit_log(event_type, detail)

