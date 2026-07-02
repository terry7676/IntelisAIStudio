from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.configuration.manager import ConfigurationManager


class ConfigurationManagerTests(unittest.TestCase):
    def test_settings_persist_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manager = ConfigurationManager(root)
            manager.initialize()
            manager.set("theme", "name", "Test Theme")

            reloaded = ConfigurationManager(root)
            reloaded.initialize()

        self.assertEqual(reloaded.get("theme", "name"), "Test Theme")


if __name__ == "__main__":
    unittest.main()

