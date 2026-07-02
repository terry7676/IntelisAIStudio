from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from terrygpt.brain.prompt_manager import PromptManager
from terrygpt.database.manager import DatabaseManager


class PromptManagerTests(unittest.TestCase):
    def test_prompt_versions_and_variables_render(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            database = DatabaseManager(Path(temp) / "prompts.sqlite")
            database.migrate()
            prompts = PromptManager(database)

            first = prompts.create("greeting", "system", "Hello {name}")
            second = prompts.create("greeting", "system", "Hi {name}")
            rendered = prompts.render("greeting", {"name": "Terry"})

        self.assertEqual(first.version, 1)
        self.assertEqual(second.version, 2)
        self.assertEqual(rendered, "Hi Terry")


if __name__ == "__main__":
    unittest.main()

