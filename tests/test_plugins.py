from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.services.plugin_service import PluginManager


class PluginTests(unittest.TestCase):
    def test_loads_sample_plugin_and_executes_command(self) -> None:
        manager = PluginManager(PROJECT_ROOT / "plugins")
        plugins = manager.load_plugins()

        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0].name, "hello_terry")

        result = manager.execute("hello_terry", "hello", name="Terry")
        self.assertIn("plugin system is working", result)


if __name__ == "__main__":
    unittest.main()

