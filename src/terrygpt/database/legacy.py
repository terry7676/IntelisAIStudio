from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from terrygpt.models import ChatMessage, Conversation, MemoryRecord


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


class TerryDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                    ON messages(conversation_id, created_at);

                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_memories_kind
                    ON memories(kind);

                CREATE TABLE IF NOT EXISTS audit_logs (
                    id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )
            try:
                connection.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_search
                    USING fts5(content, memory_id UNINDEXED)
                    """
                )
            except sqlite3.OperationalError:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_search (
                        content TEXT NOT NULL,
                        memory_id TEXT NOT NULL
                    )
                    """
                )

    def create_conversation(self, title: str) -> Conversation:
        timestamp = _now()
        conversation = Conversation(id=_new_id(), title=title, created_at=timestamp, updated_at=timestamp)
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (conversation.id, conversation.title, conversation.created_at, conversation.updated_at),
            )
        return conversation

    def list_conversations(self) -> list[Conversation]:
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
            ).fetchall()
        return [Conversation(**dict(row)) for row in rows]

    def add_message(self, conversation_id: str, role: str, content: str) -> ChatMessage:
        timestamp = _now()
        message = ChatMessage(
            id=_new_id(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            created_at=timestamp,
        )
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (message.id, message.conversation_id, message.role, message.content, message.created_at),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id),
            )
        return message

    def list_messages(self, conversation_id: str) -> list[ChatMessage]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id, conversation_id, role, content, created_at
                FROM messages
                WHERE conversation_id = ?
                ORDER BY created_at ASC
                """,
                (conversation_id,),
            ).fetchall()
        return [ChatMessage(**dict(row)) for row in rows]

    def add_memory(self, kind: str, content: str, metadata_json: str = "{}") -> MemoryRecord:
        timestamp = _now()
        memory = MemoryRecord(
            id=_new_id(),
            kind=kind,
            content=content,
            metadata_json=metadata_json,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO memories (id, kind, content, metadata_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memory.id, memory.kind, memory.content, memory.metadata_json, memory.created_at, memory.updated_at),
            )
            connection.execute("INSERT INTO memory_search (content, memory_id) VALUES (?, ?)", (memory.content, memory.id))
        return memory

    def search_memories(self, query: str, limit: int = 20) -> list[MemoryRecord]:
        clean_query = query.strip()
        if not clean_query:
            return []

        with self.connect() as connection:
            try:
                rows = connection.execute(
                    """
                    SELECT m.id, m.kind, m.content, m.metadata_json, m.created_at, m.updated_at
                    FROM memory_search s
                    JOIN memories m ON m.id = s.memory_id
                    WHERE memory_search MATCH ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (clean_query, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = connection.execute(
                    """
                    SELECT id, kind, content, metadata_json, created_at, updated_at
                    FROM memories
                    WHERE content LIKE ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                    """,
                    (f"%{clean_query}%", limit),
                ).fetchall()

        return [MemoryRecord(**dict(row)) for row in rows]

    def add_audit_log(self, event_type: str, detail: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO audit_logs (id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
                (_new_id(), event_type, detail, _now()),
            )
