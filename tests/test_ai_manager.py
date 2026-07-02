from __future__ import annotations

import unittest

from test_brain_helpers import build_test_core

from terrygpt.brain.manager import AIManager


class AIManagerTests(unittest.TestCase):
    def test_stream_response_saves_messages_and_usage(self) -> None:
        temp, core = build_test_core()
        try:
            ai = AIManager()
            core.register(ai)
            core.initialize()

            ai.update_settings(provider_name="fake", default_model="fake-model")
            chunks = list(ai.stream_response(None, "Remember that I like blue dashboards."))
            conversation_id = chunks[-1].conversation_id
            messages = ai.messages(conversation_id)
            usage_rows = ai.database.fetch_all("SELECT total_tokens FROM token_usage")  # type: ignore[union-attr]
        finally:
            temp.cleanup()

        self.assertEqual("".join(chunk.content for chunk in chunks), "Hello Terry")
        self.assertEqual([message.role for message in messages], ["user", "assistant"])
        self.assertGreaterEqual(usage_rows[0]["total_tokens"], 13)

    def test_no_model_returns_error_chunk_without_crashing(self) -> None:
        temp, core = build_test_core()
        try:
            ai = AIManager()
            core.register(ai)
            core.initialize()
            ai.update_settings(provider_name="missing", default_model="")

            chunks = list(ai.stream_response(None, "Hello"))
        finally:
            temp.cleanup()

        self.assertTrue(chunks[-1].done)
        self.assertIn("No AI model", chunks[-1].error)


if __name__ == "__main__":
    unittest.main()

