from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from terrygpt.core.module import BaseModule, ModuleHealth


DEFAULT_RUNTIME_SETTINGS: dict[str, dict[str, Any]] = {
    "ai": {
        "default_provider": "ollama",
        "default_model": "",
        "temperature": 0.7,
        "top_p": 0.9,
        "maximum_tokens": 2048,
        "streaming_enabled": True,
        "memory_enabled": True,
        "system_prompt": "You are IntelisAi Studio, a local-first assistant running on the user's PC.",
    },
    "hardware": {
        "gpu_enabled": True,
        "cpu_threads": 0,
        "memory_limit_mb": 0,
    },
    "preferences": {
        "username": "Terry",
        "startup_view": "Home",
        "confirm_dangerous_actions": True,
    },
    "plugins": {
        "auto_detect": True,
        "enabled_plugins": {},
    },
    "security": {
        "api_enabled": False,
        "api_host": "127.0.0.1",
        "require_confirmation": True,
        "allow_terminal_commands": False,
    },
    "theme": {
        "name": "TerryGPT Dark",
        "density": "comfortable",
        "accent_color": "#3b82f6",
    },
    "voice": {
        "input_device": "",
        "output_device": "",
        "text_to_speech_enabled": False,
        "speech_to_text_enabled": False,
    },
    "media": {
        "enabled": True,
        "default_provider": "stable_diffusion",
        "output_directory": "data/media",
        "model_id": "runwayml/stable-diffusion-v1-5",
        "num_inference_steps": 40,
        "guidance_scale": 8.0,
        "negative_prompt": (
            "blurry, low quality, black image, dark, distorted, "
            "deformed, cropped, watermark, text"
        ),
    },
}


class ConfigurationManager(BaseModule):
    def __init__(self, project_root: Path) -> None:
        super().__init__(name="configuration")
        self.project_root = project_root
        self.settings_path = project_root / "config" / "user_settings.json"
        self._settings: dict[str, dict[str, Any]] = deepcopy(DEFAULT_RUNTIME_SETTINGS)

    def on_initialize(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        if self.settings_path.exists():
            with self.settings_path.open("r", encoding="utf-8") as file:
                loaded = json.load(file)
            self._settings = self._merge(self._settings, loaded)
        else:
            self.save()

    def get_category(self, category: str) -> dict[str, Any]:
        return deepcopy(self._settings.get(category, {}))

    def get(self, category: str, key: str, default: Any = None) -> Any:
        return deepcopy(self._settings.get(category, {}).get(key, default))

    def set(self, category: str, key: str, value: Any) -> None:
        self._settings.setdefault(category, {})[key] = value
        self.save()
        if self.context is not None:
            self.context.event_bus.publish(
                "configuration.changed",
                {"category": category, "key": key},
                source=self.name,
            )

    def save(self) -> None:
        temporary_path = self.settings_path.with_suffix(".json.tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(self._settings, file, indent=2, sort_keys=True)
            file.write("\n")
        temporary_path.replace(self.settings_path)

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=self.settings_path.exists(),
            detail=f"Runtime settings at {self.settings_path}",
        )

    def _merge(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(base)
        for key, value in override.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = self._merge(result[key], value)
            else:
                result[key] = value
        return result
