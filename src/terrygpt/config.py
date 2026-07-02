from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class DatabaseSettings:
    path: Path


@dataclass(frozen=True)
class LoggingSettings:
    path: Path
    level: str


@dataclass(frozen=True)
class OllamaSettings:
    base_url: str
    default_model: str
    request_timeout_seconds: int


@dataclass(frozen=True)
class ApiSettings:
    host: str
    port: int
    token_path: Path


@dataclass(frozen=True)
class PluginSettings:
    directory: Path


@dataclass(frozen=True)
class DesktopSettings:
    start_api_with_desktop: bool


@dataclass(frozen=True)
class TerryConfig:
    project_root: Path
    database: DatabaseSettings
    logging: LoggingSettings
    ollama: OllamaSettings
    api: ApiSettings
    plugins: PluginSettings
    desktop: DesktopSettings


def _read_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        return tomllib.load(file)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ValueError(f"Config section [{name}] must be a table.")
    return value


def _resolve_path(root: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve()


def _project_root_from(config_path: Path | None) -> Path:
    env_root = os.environ.get("TERRYGPT_HOME")
    if env_root:
        return Path(env_root).expanduser().resolve()
    if config_path:
        return config_path.expanduser().resolve().parents[1]
    return Path.cwd().resolve()


def load_config(config_path: Path | None = None) -> TerryConfig:
    root = _project_root_from(config_path)
    default_path = root / "config" / "default.toml"
    if not default_path.exists():
        raise FileNotFoundError(f"Missing default config file: {default_path}")

    data = _read_toml(default_path)

    local_path = config_path.expanduser().resolve() if config_path else root / "config" / "local.toml"
    if local_path.exists() and local_path != default_path:
        data = _deep_merge(data, _read_toml(local_path))

    database = _section(data, "database")
    logging = _section(data, "logging")
    ollama = _section(data, "ollama")
    api = _section(data, "api")
    plugins = _section(data, "plugins")
    desktop = _section(data, "desktop")

    return TerryConfig(
        project_root=root,
        database=DatabaseSettings(path=_resolve_path(root, str(database.get("path", "data/terrygpt.sqlite")))),
        logging=LoggingSettings(
            path=_resolve_path(root, str(logging.get("path", "data/logs/terrygpt.log"))),
            level=str(logging.get("level", "INFO")).upper(),
        ),
        ollama=OllamaSettings(
            base_url=str(ollama.get("base_url", "http://127.0.0.1:11434")).rstrip("/"),
            default_model=str(ollama.get("default_model", "")),
            request_timeout_seconds=int(ollama.get("request_timeout_seconds", 120)),
        ),
        api=ApiSettings(
            host=str(api.get("host", "127.0.0.1")),
            port=int(api.get("port", 8765)),
            token_path=_resolve_path(root, str(api.get("token_path", "data/secrets.toml"))),
        ),
        plugins=PluginSettings(directory=_resolve_path(root, str(plugins.get("directory", "plugins")))),
        desktop=DesktopSettings(start_api_with_desktop=bool(desktop.get("start_api_with_desktop", False))),
    )

