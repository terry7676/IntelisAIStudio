from __future__ import annotations

import importlib.util
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from terrygpt.core.module import BaseModule, ModuleHealth
from terrygpt.database.manager import DatabaseManager


@dataclass(frozen=True)
class PluginManifest:
    name: str
    version: str
    description: str
    enabled: bool
    dependencies: tuple[str, ...]


@dataclass(frozen=True)
class PluginRecord:
    manifest: PluginManifest
    path: Path
    status: str
    missing_dependencies: tuple[str, ...]


class PluginLoader(BaseModule):
    def __init__(self, plugin_directory: Path) -> None:
        super().__init__(name="plugin_loader", dependencies=("database",))
        self.plugin_directory = plugin_directory
        self._plugins: dict[str, PluginRecord] = {}

    def on_initialize(self) -> None:
        self.plugin_directory.mkdir(parents=True, exist_ok=True)
        self.detect_plugins()

    def detect_plugins(self) -> list[PluginRecord]:
        records: list[PluginRecord] = []
        for child in sorted(self.plugin_directory.iterdir()):
            if not child.is_dir():
                continue
            try:
                record = self._inspect_plugin(child)
            except Exception as exc:
                if self.context is not None:
                    self.context.event_bus.publish(
                        "plugin.load.failed",
                        {"path": str(child), "error": str(exc)},
                        source=self.name,
                    )
                continue
            self._plugins[record.manifest.name] = record
            records.append(record)
            self._persist(record)
        if self.context is not None:
            self.context.event_bus.publish(
                "plugin.detected",
                {"count": len(records), "plugins": [record.manifest.name for record in records]},
                source=self.name,
            )
        return records

    def list_plugins(self) -> list[PluginRecord]:
        return list(self._plugins.values())

    def enable(self, name: str) -> None:
        record = self._plugins[name]
        manifest = PluginManifest(
            name=record.manifest.name,
            version=record.manifest.version,
            description=record.manifest.description,
            enabled=True,
            dependencies=record.manifest.dependencies,
        )
        updated = PluginRecord(manifest=manifest, path=record.path, status="enabled", missing_dependencies=record.missing_dependencies)
        self._plugins[name] = updated
        self._persist(updated)

    def disable(self, name: str) -> None:
        record = self._plugins[name]
        manifest = PluginManifest(
            name=record.manifest.name,
            version=record.manifest.version,
            description=record.manifest.description,
            enabled=False,
            dependencies=record.manifest.dependencies,
        )
        updated = PluginRecord(manifest=manifest, path=record.path, status="disabled", missing_dependencies=record.missing_dependencies)
        self._plugins[name] = updated
        self._persist(updated)

    def install(self, source_directory: Path) -> PluginRecord:
        record = self._inspect_plugin(source_directory)
        target = self.plugin_directory / record.manifest.name
        if target.exists():
            raise FileExistsError(f"Plugin already installed: {record.manifest.name}")
        shutil.copytree(source_directory, target)
        installed = self._inspect_plugin(target)
        self._plugins[installed.manifest.name] = installed
        self._persist(installed)
        return installed

    def uninstall(self, name: str, confirmed: bool = False) -> None:
        if not confirmed:
            raise PermissionError("Plugin uninstall requires confirmation.")
        record = self._plugins[name]
        shutil.rmtree(record.path)
        self._plugins.pop(name, None)
        if self.context is not None:
            self.context.event_bus.publish("plugin.uninstalled", {"name": name}, source=self.name)

    def version_changed(self, name: str, known_version: str) -> bool:
        record = self._plugins[name]
        return self._version_tuple(record.manifest.version) != self._version_tuple(known_version)

    def health(self) -> ModuleHealth:
        broken = [record.manifest.name for record in self._plugins.values() if record.missing_dependencies]
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=not broken,
            detail=f"{len(self._plugins)} plugin(s), {len(broken)} with missing dependencies",
        )

    def _inspect_plugin(self, path: Path) -> PluginRecord:
        manifest_path = path / "manifest.json"
        plugin_path = path / "plugin.py"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Missing manifest.json in {path}")
        if not plugin_path.exists():
            raise FileNotFoundError(f"Missing plugin.py in {path}")

        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        dependencies = tuple(str(item) for item in manifest_data.get("dependencies", []))
        missing = tuple(dependency for dependency in dependencies if importlib.util.find_spec(dependency) is None)
        manifest = PluginManifest(
            name=str(manifest_data["name"]),
            version=str(manifest_data["version"]),
            description=str(manifest_data.get("description", "")),
            enabled=bool(manifest_data.get("enabled", True)) and not missing,
            dependencies=dependencies,
        )
        status = "missing_dependencies" if missing else ("enabled" if manifest.enabled else "disabled")
        return PluginRecord(manifest=manifest, path=path, status=status, missing_dependencies=missing)

    def _persist(self, record: PluginRecord) -> None:
        database = self._database()
        database.record_plugin(
            name=record.manifest.name,
            version=record.manifest.version,
            path=record.path,
            manifest={
                "name": record.manifest.name,
                "version": record.manifest.version,
                "description": record.manifest.description,
                "enabled": record.manifest.enabled,
                "dependencies": list(record.manifest.dependencies),
            },
            enabled=record.manifest.enabled,
            status=record.status,
        )

    def _database(self) -> DatabaseManager:
        if self.context is None or self.context.core is None:
            raise RuntimeError("PluginLoader requires CoreManager access.")
        database = self.context.core.module("database")
        if not isinstance(database, DatabaseManager):
            raise RuntimeError("Registered database module is invalid.")
        return database

    def _version_tuple(self, version: str) -> tuple[int, ...]:
        parts = []
        for chunk in version.split("."):
            try:
                parts.append(int(chunk))
            except ValueError:
                parts.append(0)
        return tuple(parts)

