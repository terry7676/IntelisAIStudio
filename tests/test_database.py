from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.database import TerryDatabase


class DatabaseTests(unittest.TestCase):
    def test_conversation_message_and_memory_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = TerryDatabase(Path(temp) / "terry.sqlite")
            database.initialize()

            conversation = database.create_conversation("Test chat")
            database.add_message(conversation.id, "user", "Remember the blue folder.")
            database.add_memory("note", "The blue folder is important.")

            messages = database.list_messages(conversation.id)
            memories = database.search_memories("blue")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].role, "user")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].kind, "note")


if __name__ == "__main__":
    unittest.main()

