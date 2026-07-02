from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.security.manager import SecurityManager


class SecurityManagerTests(unittest.TestCase):
    def test_dangerous_action_requires_confirmation(self) -> None:
        security = SecurityManager()

        with self.assertRaises(PermissionError):
            security.safe_execute("user", "delete_file", confirmed=False)

        security.safe_execute("user", "delete_file", confirmed=True)


if __name__ == "__main__":
    unittest.main()

