from __future__ import annotations

import importlib.util
import platform
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from terrygpt.core.module import BaseModule, ModuleHealth


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    detail: str
    required: bool = False


class DependencyChecker(BaseModule):
    def __init__(self, project_root: Path) -> None:
        super().__init__(name="dependency_checker")
        self.project_root = project_root
        self.statuses: list[DependencyStatus] = []

    def on_initialize(self) -> None:
        self.statuses = self.check_all()
        if self.context is not None:
            self.context.event_bus.publish(
                "dependencies.checked",
                {"statuses": [status.__dict__ for status in self.statuses]},
                source=self.name,
            )

    def check_all(self) -> list[DependencyStatus]:
        return [
            self._python_status(),
            self._module_status("PySide6", required=True),
            self._module_status("fastapi", required=True),
            self._sqlite_status(),
            self._ollama_status(),
            self._whisper_status(),
            self._executable_status("ffmpeg", required=False),
            self._real_esrgan_status(),
            self._tesseract_status(),
            self._gpu_status(),
        ]

    def health(self) -> ModuleHealth:
        required_ok = all(status.available for status in self.statuses if status.required)
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=required_ok,
            detail=f"{sum(1 for status in self.statuses if status.available)}/{len(self.statuses)} checks available",
        )

    def _python_status(self) -> DependencyStatus:
        version = sys.version_info
        return DependencyStatus(
            name="Python",
            available=version >= (3, 13),
            detail=platform.python_version(),
            required=True,
        )

    def _module_status(self, module_name: str, required: bool) -> DependencyStatus:
        available = importlib.util.find_spec(module_name) is not None
        return DependencyStatus(
            name=module_name,
            available=available,
            detail="Python module importable" if available else "Python module not found",
            required=required,
        )

    def _sqlite_status(self) -> DependencyStatus:
        import sqlite3

        return DependencyStatus(name="SQLite", available=True, detail=sqlite3.sqlite_version, required=True)

    def _executable_status(self, executable: str, required: bool) -> DependencyStatus:
        path = shutil.which(executable)
        return DependencyStatus(
            name=executable,
            available=path is not None,
            detail=path or "Executable not found on PATH",
            required=required,
        )

    def _ollama_status(self) -> DependencyStatus:
        executable = shutil.which("ollama")
        api_available = False
        try:
            with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as response:
                api_available = response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            api_available = False
        return DependencyStatus(
            name="Ollama",
            available=bool(executable or api_available),
            detail="Ollama API reachable" if api_available else (executable or "Ollama not detected"),
            required=False,
        )

    def _whisper_status(self) -> DependencyStatus:
        module_available = importlib.util.find_spec("whisper") is not None
        executable = shutil.which("whisper")
        return DependencyStatus(
            name="Whisper",
            available=bool(module_available or executable),
            detail="Python module importable" if module_available else (executable or "Whisper not detected"),
            required=False,
        )

    def _real_esrgan_status(self) -> DependencyStatus:
        names = ("realesrgan-ncnn-vulkan", "realesrgan", "realesrgan.exe")
        found = next((path for name in names if (path := shutil.which(name))), None)
        return DependencyStatus(
            name="Real-ESRGAN",
            available=found is not None,
            detail=found or "Real-ESRGAN executable not found on PATH",
            required=False,
        )

    def _tesseract_status(self) -> DependencyStatus:
        return self._executable_status("tesseract", required=False)

    def _gpu_status(self) -> DependencyStatus:
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return DependencyStatus(name="GPU", available=False, detail="nvidia-smi not found", required=False)
        try:
            result = subprocess.run(
                [nvidia_smi, "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except OSError as exc:
            return DependencyStatus(name="GPU", available=False, detail=str(exc), required=False)
        name = result.stdout.strip().splitlines()[0] if result.stdout.strip() else "NVIDIA GPU detected"
        return DependencyStatus(name="GPU", available=result.returncode == 0, detail=name, required=False)

