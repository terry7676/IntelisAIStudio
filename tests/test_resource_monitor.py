from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.resources.monitor import ResourceMonitor


class ResourceMonitorTests(unittest.TestCase):
    def test_snapshot_returns_disk_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            monitor = ResourceMonitor(Path(temp))
            snapshot = monitor.snapshot()

        self.assertIsNotNone(snapshot.disk_total_gb)
        self.assertIsNotNone(snapshot.disk_used_gb)


if __name__ == "__main__":
    unittest.main()

