from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from terrygpt.brain.conversation_manager import ConversationManager
from terrygpt.brain.models import ConversationStatus
from terrygpt.database.manager import DatabaseManager


class ConversationManagerTests(unittest.TestCase):
    def test_rename_archive_restore_delete_and_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = DatabaseManager(Path(temp) / "conversation.sqlite")
            database.migrate()
            conversations = ConversationManager(database)

            conversation = conversations.create("Original")
            conversations.add_message(conversation.id, "user", "Find my roadmap notes.")
            renamed = conversations.rename(conversation.id, "Roadmap")
            archived = conversations.archive(conversation.id)
            restored = conversations.restore(conversation.id)
            found = conversations.search("roadmap")
            conversations.delete(conversation.id)

        self.assertEqual(renamed.title, "Roadmap")
        self.assertEqual(archived.status, ConversationStatus.ARCHIVED)
        self.assertEqual(restored.status, ConversationStatus.ACTIVE)
        self.assertEqual(found[0].id, conversation.id)


if __name__ == "__main__":
    unittest.main()

