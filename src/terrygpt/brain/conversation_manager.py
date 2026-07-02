from __future__ import annotations

import json

from terrygpt.brain.models import ConversationRecord, ConversationStatus, MessageRecord
from terrygpt.database.manager import DatabaseManager, new_id, utc_now


class ConversationManager:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def create(self, title: str = "New chat", provider_name: str = "", model_name: str = "") -> ConversationRecord:
        timestamp = utc_now()
        conversation_id = new_id()
        clean_title = title.strip()[:120] or "New chat"
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO conversations
                    (id, title, status, provider_name, model_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (conversation_id, clean_title, ConversationStatus.ACTIVE, provider_name, model_name, timestamp, timestamp),
            )
        return self.get(conversation_id)

    def get(self, conversation_id: str) -> ConversationRecord:
        row = self.database.fetch_one(
            """
            SELECT id, title, status, created_at, updated_at, archived_at, summary, model_name, provider_name
            FROM conversations
            WHERE id = ? AND deleted_at IS NULL
            """,
            (conversation_id,),
        )
        if row is None:
            raise KeyError(f"Conversation not found: {conversation_id}")
        return ConversationRecord(
            id=str(row["id"]),
            title=str(row["title"]),
            status=ConversationStatus(str(row["status"])),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            archived_at=row["archived_at"],
            summary=str(row["summary"]),
            model_name=str(row["model_name"]),
            provider_name=str(row["provider_name"]),
        )

    def list(self, include_archived: bool = False) -> list[ConversationRecord]:
        statuses = ("active", "archived") if include_archived else ("active",)
        sql_markers = ",".join("?" for _ in statuses)
        rows = self.database.fetch_all(
            f"""
            SELECT id, title, status, created_at, updated_at, archived_at, summary, model_name, provider_name
            FROM conversations
            WHERE deleted_at IS NULL AND status IN ({sql_markers})
            ORDER BY updated_at DESC
            """,
            statuses,
        )
        return [
            ConversationRecord(
                id=str(row["id"]),
                title=str(row["title"]),
                status=ConversationStatus(str(row["status"])),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
                archived_at=row["archived_at"],
                summary=str(row["summary"]),
                model_name=str(row["model_name"]),
                provider_name=str(row["provider_name"]),
            )
            for row in rows
        ]

    def rename(self, conversation_id: str, title: str) -> ConversationRecord:
        clean_title = title.strip()[:120]
        if not clean_title:
            raise ValueError("Conversation title cannot be empty.")
        self.database.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (clean_title, utc_now(), conversation_id),
        )
        return self.get(conversation_id)

    def archive(self, conversation_id: str) -> ConversationRecord:
        timestamp = utc_now()
        self.database.execute(
            "UPDATE conversations SET status = ?, archived_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (ConversationStatus.ARCHIVED, timestamp, timestamp, conversation_id),
        )
        return self.get(conversation_id)

    def restore(self, conversation_id: str) -> ConversationRecord:
        timestamp = utc_now()
        self.database.execute(
            "UPDATE conversations SET status = ?, archived_at = NULL, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (ConversationStatus.ACTIVE, timestamp, conversation_id),
        )
        return self.get(conversation_id)

    def delete(self, conversation_id: str) -> None:
        timestamp = utc_now()
        self.database.execute(
            "UPDATE conversations SET status = ?, deleted_at = ?, updated_at = ? WHERE id = ?",
            (ConversationStatus.DELETED, timestamp, timestamp, conversation_id),
        )

    def search(self, query: str, limit: int = 20) -> list[ConversationRecord]:
        clean_query = query.strip()
        if not clean_query:
            return []
        rows = self.database.fetch_all(
            """
            SELECT DISTINCT c.id, c.title, c.status, c.created_at, c.updated_at, c.archived_at,
                            c.summary, c.model_name, c.provider_name
            FROM conversations c
            LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.deleted_at IS NULL
              AND (c.title LIKE ? OR c.summary LIKE ? OR m.content LIKE ?)
            ORDER BY c.updated_at DESC
            LIMIT ?
            """,
            (f"%{clean_query}%", f"%{clean_query}%", f"%{clean_query}%", limit),
        )
        return [
            ConversationRecord(
                id=str(row["id"]),
                title=str(row["title"]),
                status=ConversationStatus(str(row["status"])),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
                archived_at=row["archived_at"],
                summary=str(row["summary"]),
                model_name=str(row["model_name"]),
                provider_name=str(row["provider_name"]),
            )
            for row in rows
        ]

    def add_message(self, conversation_id: str, role: str, content: str, metadata: dict[str, object] | None = None) -> MessageRecord:
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Message content cannot be empty.")
        timestamp = utc_now()
        token_count = self.estimate_tokens(clean_content)
        metadata_json = json.dumps(metadata or {}, sort_keys=True)
        message_id = new_id()
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO messages (id, conversation_id, role, content, token_count, metadata_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (message_id, conversation_id, role, clean_content, token_count, metadata_json, timestamp),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (timestamp, conversation_id),
            )
        return MessageRecord(message_id, conversation_id, role, clean_content, token_count, metadata or {}, timestamp)

    def messages(self, conversation_id: str, limit: int | None = None) -> list[MessageRecord]:
        sql = """
            SELECT id, conversation_id, role, content, token_count, metadata_json, created_at
            FROM messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC
        """
        parameters: tuple[object, ...] = (conversation_id,)
        if limit is not None:
            sql += " LIMIT ?"
            parameters = (conversation_id, limit)
        rows = self.database.fetch_all(sql, parameters)
        return [
            MessageRecord(
                id=str(row["id"]),
                conversation_id=str(row["conversation_id"]),
                role=str(row["role"]),
                content=str(row["content"]),
                token_count=int(row["token_count"]),
                metadata=json.loads(str(row["metadata_json"])),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def update_summary(self, conversation_id: str, summary: str) -> None:
        timestamp = utc_now()
        with self.database.connect() as connection:
            message_count = connection.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            ).fetchone()["count"]
            connection.execute(
                "UPDATE conversations SET summary = ?, updated_at = ? WHERE id = ?",
                (summary, timestamp, conversation_id),
            )
            connection.execute(
                """
                INSERT INTO conversation_summaries (id, conversation_id, summary, message_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (new_id(), conversation_id, summary, int(message_count), timestamp),
            )

    def estimate_tokens(self, text: str) -> int:
        if not text.strip():
            return 0
        return max(1, int(len(text.split()) * 1.35))
