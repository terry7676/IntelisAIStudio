from __future__ import annotations

from pathlib import Path

from terrygpt.app.bootstrap import run_desktop as run_core_desktop


def run_desktop(config_path: Path | None = None) -> int:
    return run_core_desktop(config_path=config_path)
