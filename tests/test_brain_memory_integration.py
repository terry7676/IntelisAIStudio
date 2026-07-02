from __future__ import annotations

import unittest

from test_brain_helpers import build_test_core

from terrygpt.brain.conversation_manager import ConversationManager
from terrygpt.brain.memory_integration import BrainMemoryIntegration


class BrainMemoryIntegrationTests(unittest.TestCase):
    def test_important_conversation_is_remembered(self) -> None:
        temp, core = build_test_core()
        try:
            core.initialize()
            conversations = ConversationManager(core.module("database"))  # type: ignore[arg-type]
            memory = core.module("memory_engine")
            conversation = conversations.create("Memory")
            integration = BrainMemoryIntegration(conversations, memory)  # type: ignore[arg-type]
            integration.update_after_response(
                conversation.id,
                "Remember that I prefer compact dashboards.",
                "I will remember that preference.",
                "fake-model",
            )
            results = memory.search("compact dashboards")  # type: ignore[attr-defined]
        finally:
            temp.cleanup()

        self.assertGreaterEqual(len(results), 1)


if __name__ == "__main__":
    unittest.main()

