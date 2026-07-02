from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.database.manager import DatabaseManager


class DatabaseMigrationTests(unittest.TestCase):
    def test_migrations_create_required_tables(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manager = DatabaseManager(Path(temp) / "test.sqlite")
            manager.migrate()
            tables = {
                row["name"]
                for row in manager.fetch_all("SELECT name FROM sqlite_master WHERE type IN ('table', 'virtual table')")
            }

        self.assertIn("users", tables)
        self.assertIn("conversations", tables)
        self.assertIn("messages", tables)
        self.assertIn("memory", tables)
        self.assertIn("projects", tables)
        self.assertIn("tasks", tables)
        self.assertIn("plugins", tables)
        self.assertIn("settings", tables)
        self.assertIn("history", tables)
        self.assertIn("agents", tables)

    def test_migrations_repair_phase_one_conversation_table(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            manager = DatabaseManager(Path(temp) / "legacy.sqlite")
            with manager.connect() as connection:
                connection.executescript(
                    """
                    CREATE TABLE conversations (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    );
                    CREATE TABLE messages (
                        id TEXT PRIMARY KEY,
                        conversation_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )

            manager.migrate()
            columns = {
                row["name"]
                for row in manager.fetch_all("PRAGMA table_info(conversations)")
            }

        self.assertIn("status", columns)
        self.assertIn("user_id", columns)
        self.assertIn("archived_at", columns)


if __name__ == "__main__":
    unittest.main()
