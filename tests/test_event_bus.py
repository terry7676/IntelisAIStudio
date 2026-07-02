from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.core.events import EventBus


class EventBusTests(unittest.TestCase):
    def test_publish_delivers_event_and_records_history(self) -> None:
        bus = EventBus()
        received = []
        bus.subscribe("user.message", received.append)

        event = bus.publish("user.message", {"text": "hello"}, source="test")

        self.assertEqual(received[0], event)
        self.assertEqual(bus.history(1)[0].payload["text"], "hello")


if __name__ == "__main__":
    unittest.main()

