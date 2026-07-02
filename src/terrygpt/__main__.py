from __future__ import annotations

import argparse
from pathlib import Path

from terrygpt.app.bootstrap import initialize_core, run_desktop


def _init_project(config_path: str | None) -> int:
    core = initialize_core(Path(config_path) if config_path else None)
    config = core.context.config
    plugins = getattr(core.module("plugin_loader"), "list_plugins")()
    core.stop()

    print("TerryGPT initialized.")
    print(f"Project folder: {config.project_root}")
    print(f"Database: {config.database.path}")
    print(f"Log file: {config.logging.path}")
    print(f"Plugins loaded: {len(plugins)}")
    print("API token file was created or reused. Do not share it.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="terrygpt")
    parser.add_argument("--config", help="Path to a TOML config file.")

    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("init", help="Create local data files.")
    subparsers.add_parser("desktop", help="Start the PySide6 desktop app.")
    subparsers.add_parser("server", help="Start the FastAPI backend.")

    args = parser.parse_args(argv)
    command = args.command or "desktop"

    if command == "init":
        return _init_project(args.config)

    if command == "server":
        from terrygpt.api.server import main as server_main

        return server_main(["--config", args.config] if args.config else None)

    if command == "desktop":
        return run_desktop(config_path=Path(args.config) if args.config else None)

    parser.error(f"Unknown command: {command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
