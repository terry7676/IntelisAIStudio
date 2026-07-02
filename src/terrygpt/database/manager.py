from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

from terrygpt.core.module import BaseModule, ModuleHealth


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


CORE_MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="core_schema",
        sql="""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant', 'tool')),
            content TEXT NOT NULL,
            token_count INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS memory (
            id TEXT PRIMARY KEY,
            memory_type TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            importance INTEGER NOT NULL DEFAULT 50,
            expires_at TEXT,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_accessed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            path TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL,
            priority INTEGER NOT NULL DEFAULT 100,
            progress INTEGER NOT NULL DEFAULT 0,
            retries INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 0,
            payload_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT NOT NULL DEFAULT '{}',
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS plugins (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            version TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            installed_path TEXT NOT NULL,
            manifest_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'installed',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            category TEXT NOT NULL,
            value_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS history (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """,
    ),
    Migration(
        version=2,
        name="core_indexes",
        sql="""
        CREATE INDEX IF NOT EXISTS idx_messages_conversation
            ON messages(conversation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_memory_type
            ON memory(memory_type);
        CREATE INDEX IF NOT EXISTS idx_memory_expiration
            ON memory(expires_at);
        CREATE INDEX IF NOT EXISTS idx_tasks_status_priority
            ON tasks(status, priority, created_at);
        CREATE INDEX IF NOT EXISTS idx_history_type
            ON history(event_type, created_at);
        """,
    ),
    Migration(
        version=3,
        name="brain_schema",
        sql="""
        ALTER TABLE conversations ADD COLUMN archived_at TEXT;
        ALTER TABLE conversations ADD COLUMN summary TEXT NOT NULL DEFAULT '';
        ALTER TABLE conversations ADD COLUMN model_name TEXT NOT NULL DEFAULT '';
        ALTER TABLE conversations ADD COLUMN provider_name TEXT NOT NULL DEFAULT '';
        ALTER TABLE conversations ADD COLUMN deleted_at TEXT;

        CREATE TABLE IF NOT EXISTS prompt_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            prompt_type TEXT NOT NULL CHECK (prompt_type IN ('system', 'user', 'agent')),
            version INTEGER NOT NULL,
            template TEXT NOT NULL,
            variables_json TEXT NOT NULL DEFAULT '[]',
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(name, version)
        );

        CREATE TABLE IF NOT EXISTS ai_request_logs (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            provider_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            response_time_ms INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS ai_model_cache (
            id TEXT PRIMARY KEY,
            provider_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            parameter_size TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            quantization TEXT NOT NULL DEFAULT '',
            context_length INTEGER NOT NULL DEFAULT 0,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            detected_at TEXT NOT NULL,
            UNIQUE(provider_name, model_name)
        );

        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            message_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS token_usage (
            id TEXT PRIMARY KEY,
            conversation_id TEXT,
            provider_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            prompt_tokens INTEGER NOT NULL DEFAULT 0,
            completion_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_conversations_status_updated
            ON conversations(status, updated_at);
        CREATE INDEX IF NOT EXISTS idx_prompt_templates_name_active
            ON prompt_templates(name, active);
        CREATE INDEX IF NOT EXISTS idx_ai_request_logs_conversation
            ON ai_request_logs(conversation_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_token_usage_conversation
            ON token_usage(conversation_id, created_at);
        """,
    ),
)


class DatabaseManager(BaseModule):
    def __init__(self, database_path: Path) -> None:
        super().__init__(name="database")
        self.database_path = database_path
        self.fts_available = False

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def on_initialize(self) -> None:
        self.migrate()
        if self.context is not None:
            self.context.event_bus.subscribe("security.audit", self._record_audit_event)
            self.context.event_bus.subscribe("history.record", self._record_history_event)

    def migrate(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                )
                """
            )
            applied = {
                int(row["version"])
                for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
            }
            for migration in CORE_MIGRATIONS:
                if migration.version not in applied:
                    self._apply_migration(connection, migration)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                        (migration.version, migration.name, utc_now()),
                    )
            self._ensure_legacy_columns(connection)
            self._ensure_memory_search(connection)

    def _apply_migration(self, connection: sqlite3.Connection, migration: Migration) -> None:
        if migration.version != 3:
            connection.executescript(migration.sql)
            return
        alter_statements: list[str] = []
        create_statements: list[str] = []
        for statement in migration.sql.split(";"):
            clean = statement.strip()
            if not clean:
                continue
            if clean.upper().startswith("ALTER TABLE"):
                alter_statements.append(clean)
            else:
                create_statements.append(clean)
        for statement in alter_statements:
            try:
                connection.execute(statement)
            except sqlite3.OperationalError as exc:
                if "duplicate column name" not in str(exc).lower():
                    raise
        self._ensure_legacy_columns(connection)
        for statement in create_statements:
            connection.execute(statement)

    def _ensure_legacy_columns(self, connection: sqlite3.Connection) -> None:
        self._ensure_columns(
            connection,
            "conversations",
            {
                "user_id": "TEXT",
                "status": "TEXT NOT NULL DEFAULT 'active'",
                "archived_at": "TEXT",
                "summary": "TEXT NOT NULL DEFAULT ''",
                "model_name": "TEXT NOT NULL DEFAULT ''",
                "provider_name": "TEXT NOT NULL DEFAULT ''",
                "deleted_at": "TEXT",
            },
        )
        self._ensure_columns(
            connection,
            "messages",
            {
                "token_count": "INTEGER NOT NULL DEFAULT 0",
                "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
            },
        )

    def _ensure_columns(self, connection: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
        existing = {
            str(row["name"])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for column, definition in columns.items():
            if column not in existing:
                connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _ensure_memory_search(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_search
                USING fts5(content, memory_id UNINDEXED)
                """
            )
            self.fts_available = True
        except sqlite3.OperationalError:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_search (
                    content TEXT NOT NULL,
                    memory_id TEXT NOT NULL
                )
                """
            )
            self.fts_available = False

    def applied_migrations(self) -> list[int]:
        with self.connect() as connection:
            rows = connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall()
        return [int(row["version"]) for row in rows]

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=self.database_path.exists(),
            detail=f"SQLite database at {self.database_path}",
        )

    def execute(self, sql: str, parameters: tuple[Any, ...] = ()) -> None:
        with self.connect() as connection:
            connection.execute(sql, parameters)

    def fetch_all(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.connect() as connection:
            return connection.execute(sql, parameters).fetchall()

    def fetch_one(self, sql: str, parameters: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.connect() as connection:
            return connection.execute(sql, parameters).fetchone()

    def set_setting(self, category: str, key: str, value: Any) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO settings (key, category, value_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    category = excluded.category,
                    value_json = excluded.value_json,
                    updated_at = excluded.updated_at
                """,
                (key, category, json.dumps(value, sort_keys=True), utc_now()),
            )

    def get_setting(self, key: str, default: Any = None) -> Any:
        row = self.fetch_one("SELECT value_json FROM settings WHERE key = ?", (key,))
        if row is None:
            return default
        return json.loads(str(row["value_json"]))

    def record_plugin(self, name: str, version: str, path: Path, manifest: dict[str, Any], enabled: bool, status: str) -> None:
        timestamp = utc_now()
        with self.connect() as connection:
            existing = connection.execute("SELECT id, created_at FROM plugins WHERE name = ?", (name,)).fetchone()
            plugin_id = str(existing["id"]) if existing else new_id()
            created_at = str(existing["created_at"]) if existing else timestamp
            connection.execute(
                """
                INSERT INTO plugins (id, name, version, enabled, installed_path, manifest_json, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    version = excluded.version,
                    enabled = excluded.enabled,
                    installed_path = excluded.installed_path,
                    manifest_json = excluded.manifest_json,
                    status = excluded.status,
                    updated_at = excluded.updated_at
                """,
                (
                    plugin_id,
                    name,
                    version,
                    int(enabled),
                    str(path),
                    json.dumps(manifest, sort_keys=True),
                    status,
                    created_at,
                    timestamp,
                ),
            )

    def add_audit_log(self, event_type: str, detail: str) -> None:
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO audit_logs (id, event_type, detail, created_at) VALUES (?, ?, ?, ?)",
                (new_id(), event_type, detail, utc_now()),
            )

    def _record_audit_event(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        event_type = str(payload.get("event_type", getattr(event, "event_type", "security.audit")))
        detail = str(payload.get("detail", payload))
        self.add_audit_log(event_type, detail)

    def _record_history_event(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO history (id, event_type, summary, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    new_id(),
                    str(payload.get("event_type", getattr(event, "event_type", "history.record"))),
                    str(payload.get("summary", "")),
                    json.dumps(payload, sort_keys=True),
                    utc_now(),
                ),
            )
