from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.core.manager import CoreManager
from terrygpt.core.module import ModuleState


def write_config(root: Path) -> Path:
    (root / "config").mkdir()
    (root / "plugins").mkdir()
    path = root / "config" / "default.toml"
    path.write_text(
        """
[database]
path = "data/test.sqlite"
[logging]
path = "data/logs/application.log"
level = "INFO"
[ollama]
base_url = "http://127.0.0.1:11434"
default_model = ""
request_timeout_seconds = 1
[api]
host = "127.0.0.1"
port = 8765
token_path = "data/secrets.toml"
[plugins]
directory = "plugins"
[desktop]
start_api_with_desktop = false
""",
        encoding="utf-8",
    )
    return path


class CoreManagerTests(unittest.TestCase):
    def test_core_initializes_major_modules(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config_path = write_config(Path(temp))
            core = CoreManager.build(config_path)
            core.initialize()
            core.start()
            try:
                module_names = {module.name for module in core.modules()}
                self.assertIn("database", module_names)
                self.assertIn("memory_engine", module_names)
                self.assertIn("plugin_loader", module_names)
                self.assertIn("media_manager", module_names)
                self.assertIn("task_scheduler", module_names)
                self.assertEqual(core.module("database").state, ModuleState.STARTED)
            finally:
                core.stop()


if __name__ == "__main__":
    unittest.main()

