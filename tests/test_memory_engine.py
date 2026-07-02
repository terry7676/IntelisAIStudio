from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.core.context import CoreContext
from terrygpt.core.events import EventBus
from terrygpt.core.manager import CoreManager
from terrygpt.database.manager import DatabaseManager
from terrygpt.memory.engine import MemoryEngine


class MemoryEngineTests(unittest.TestCase):
    def test_remember_and_rank_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = DatabaseManager(Path(temp) / "memory.sqlite")
            db.migrate()
            context = CoreContext(config=None, event_bus=EventBus())  # type: ignore[arg-type]
            core = CoreManager(context)
            context.core = core
            core.register(db)
            memory = MemoryEngine()
            core.register(memory)
            memory.initialize()

            memory.remember("preference", "Terry prefers dark professional themes.", importance=90)
            results = memory.search("dark themes")

        self.assertEqual(results[0].item.memory_type, "preference")
        self.assertGreater(results[0].score, 0)


if __name__ == "__main__":
    unittest.main()

