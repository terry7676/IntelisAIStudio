from __future__ import annotations

import unittest

from test_brain_helpers import build_test_core

from terrygpt.brain.context_builder import ContextBuilder
from terrygpt.brain.conversation_manager import ConversationManager
from terrygpt.brain.models import BrainSettings
from terrygpt.brain.prompt_manager import PromptManager


class ContextBuilderTests(unittest.TestCase):
    def test_context_includes_history_memory_and_preferences(self) -> None:
        temp, core = build_test_core()
        try:
            core.initialize()
            database = core.module("database")
            conversations = ConversationManager(database)  # type: ignore[arg-type]
            prompts = PromptManager(database)  # type: ignore[arg-type]
            memory = core.module("memory_engine")
            configuration = core.module("configuration")
            configuration.set("preferences", "username", "Terry")  # type: ignore[attr-defined]
            prompts.ensure_defaults("System prompt")
            conversation = conversations.create("Context Test")
            conversations.add_message(conversation.id, "user", "Previous message")
            memory.remember("preference", "Terry likes local AI systems.", importance=80)  # type: ignore[attr-defined]

            builder = ContextBuilder(conversations, prompts, memory, configuration)  # type: ignore[arg-type]
            context = builder.build(conversation.id, "local AI", BrainSettings(provider_name="fake"))
        finally:
            temp.cleanup()

        joined = "\n".join(message.content for message in context.messages)
        self.assertIn("Previous message", joined)
        self.assertIn("Terry likes local AI systems", joined)
        self.assertIn("username", joined)


if __name__ == "__main__":
    unittest.main()

