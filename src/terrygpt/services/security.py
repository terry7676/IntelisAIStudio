from __future__ import annotations

import secrets
import tomllib
from pathlib import Path


DANGEROUS_ACTIONS = {
    "delete_file",
    "delete_folder",
    "run_terminal_command",
    "download_executable",
    "install_software",
    "send_email",
}


def requires_confirmation(action_name: str) -> bool:
    return action_name in DANGEROUS_ACTIONS


class ApiTokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def get_or_create_token(self) -> str:
        existing = self._read_token()
        if existing:
            return existing

        token = secrets.token_urlsafe(32)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(f'api_token = "{token}"\n', encoding="utf-8")
        return token

    def verify(self, provided_token: str | None) -> bool:
        token = self.get_or_create_token()
        if not provided_token:
            return False
        return secrets.compare_digest(token, provided_token)

    def _read_token(self) -> str | None:
        if not self.path.exists():
            return None
        with self.path.open("rb") as file:
            data = tomllib.load(file)
        token = data.get("api_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        return None

