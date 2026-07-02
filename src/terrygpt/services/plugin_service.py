from __future__ import annotations

import importlib.util
import json
import logging
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Protocol

from terrygpt.models import PluginInfo

LOGGER = logging.getLogger(__name__)


class TerryPlugin(Protocol):
    def commands(self) -> Mapping[str, Callable[..., str]]:
        raise NotImplementedError


class PluginManager:
    def __init__(self, plugin_directory: Path) -> None:
        self.plugin_directory = plugin_directory
        self._plugins: dict[str, TerryPlugin] = {}
        self._infos: dict[str, PluginInfo] = {}

    def load_plugins(self) -> list[PluginInfo]:
        self.plugin_directory.mkdir(parents=True, exist_ok=True)
        self._plugins.clear()
        self._infos.clear()

        for child in sorted(self.plugin_directory.iterdir()):
            if child.is_dir():
                try:
                    info, plugin = self._load_plugin(child)
                except Exception:
                    LOGGER.exception("Failed to load plugin from %s", child)
                    continue
                self._infos[info.name] = info
                self._plugins[info.name] = plugin

        return list(self._infos.values())

    def list_plugins(self) -> list[PluginInfo]:
        return list(self._infos.values())

    def execute(self, plugin_name: str, command_name: str, **kwargs: object) -> str:
        plugin = self._plugins.get(plugin_name)
        if plugin is None:
            raise KeyError(f"Plugin is not loaded: {plugin_name}")

        command = plugin.commands().get(command_name)
        if command is None:
            raise KeyError(f"Plugin '{plugin_name}' does not provide command '{command_name}'.")

        return command(**kwargs)

    def _load_plugin(self, directory: Path) -> tuple[PluginInfo, TerryPlugin]:
        manifest_path = directory / "manifest.json"
        plugin_path = directory / "plugin.py"
        if not manifest_path.exists() or not plugin_path.exists():
            raise FileNotFoundError(f"Plugin folder must include manifest.json and plugin.py: {directory}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = str(manifest["name"])
        version = str(manifest["version"])
        description = str(manifest.get("description", ""))

        module_name = f"terrygpt_user_plugin_{name.replace('-', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, plugin_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not import plugin module: {plugin_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        factory = getattr(module, "create_plugin", None)
        if not callable(factory):
            raise TypeError(f"Plugin does not define create_plugin(): {plugin_path}")

        plugin = factory()
        commands = plugin.commands()
        if not isinstance(commands, Mapping):
            raise TypeError(f"Plugin commands() must return a mapping: {plugin_path}")

        info = PluginInfo(name=name, version=version, description=description, commands=tuple(sorted(commands.keys())))
        return info, plugin
