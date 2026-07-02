from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.config import load_config


class ConfigTests(unittest.TestCase):
    def test_loads_default_config_from_project_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "config").mkdir()
            (root / "config" / "default.toml").write_text(
                """
[database]
path = "data/app.sqlite"
[logging]
path = "data/logs/app.log"
level = "INFO"
[ollama]
base_url = "http://127.0.0.1:11434"
default_model = ""
request_timeout_seconds = 30
[api]
host = "127.0.0.1"
port = 9000
token_path = "data/secrets.toml"
[plugins]
directory = "plugins"
[desktop]
start_api_with_desktop = false
""",
                encoding="utf-8",
            )

            old_cwd = Path.cwd()
            try:
                import os

                os.chdir(root)
                config = load_config()
            finally:
                os.chdir(old_cwd)

        self.assertEqual(config.api.port, 9000)
        self.assertEqual(config.database.path.name, "app.sqlite")


if __name__ == "__main__":
    unittest.main()

