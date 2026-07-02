from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.core.context import CoreContext
from terrygpt.core.events import EventBus
from terrygpt.core.manager import CoreManager
from terrygpt.database.manager import DatabaseManager
from terrygpt.tasks.scheduler import TaskScheduler, TaskStatus


class TaskSchedulerTests(unittest.TestCase):
    def test_task_completes_with_progress(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = DatabaseManager(Path(temp) / "tasks.sqlite")
            db.migrate()
            context = CoreContext(config=None, event_bus=EventBus())  # type: ignore[arg-type]
            core = CoreManager(context)
            context.core = core
            core.register(db)
            scheduler = TaskScheduler()
            core.register(scheduler)
            scheduler.initialize()
            scheduler.register_handler("test", lambda payload, progress, cancel: {"ok": True})
            scheduler.start()
            try:
                task_id = scheduler.submit("Test task", "test")
                deadline = time.time() + 5
                while scheduler.get(task_id).status not in {TaskStatus.COMPLETED, TaskStatus.FAILED} and time.time() < deadline:
                    time.sleep(0.05)
            finally:
                scheduler.stop()

        self.assertEqual(scheduler.get(task_id).status, TaskStatus.COMPLETED)


if __name__ == "__main__":
    unittest.main()

