from __future__ import annotations

import ctypes
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from terrygpt.core.module import BaseModule, ModuleHealth


@dataclass(frozen=True)
class ResourceSnapshot:
    cpu_percent: float | None
    ram_used_mb: int | None
    ram_total_mb: int | None
    disk_used_gb: float | None
    disk_total_gb: float | None
    network_received_mb: float | None
    network_sent_mb: float | None
    gpu_percent: float | None
    gpu_memory_used_mb: int | None
    gpu_memory_total_mb: int | None


class _MemoryStatus(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


class WindowsCpuSampler:
    def __init__(self) -> None:
        self._last_idle: int | None = None
        self._last_total: int | None = None

    def sample(self) -> float | None:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        idle = _FileTime()
        kernel = _FileTime()
        user = _FileTime()
        if not kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            return None
        idle_ticks = self._to_int(idle)
        total_ticks = self._to_int(kernel) + self._to_int(user)
        if self._last_idle is None or self._last_total is None:
            self._last_idle = idle_ticks
            self._last_total = total_ticks
            return None
        idle_delta = idle_ticks - self._last_idle
        total_delta = total_ticks - self._last_total
        self._last_idle = idle_ticks
        self._last_total = total_ticks
        if total_delta <= 0:
            return None
        return max(0.0, min(100.0, 100.0 * (1.0 - (idle_delta / total_delta))))

    def _to_int(self, value: _FileTime) -> int:
        return (int(value.dwHighDateTime) << 32) + int(value.dwLowDateTime)


class ResourceMonitor(BaseModule):
    def __init__(self, project_root: Path, interval_seconds: float = 2.0) -> None:
        super().__init__(name="resource_monitor")
        self.project_root = project_root
        self.interval_seconds = interval_seconds
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._last_snapshot = ResourceSnapshot(None, None, None, None, None, None, None, None, None, None)
        self._cpu_sampler = WindowsCpuSampler() if hasattr(ctypes, "windll") else None

    def on_start(self) -> None:
        self._stopping.clear()
        self._thread = threading.Thread(target=self._loop, name="TerryGPTResourceMonitor", daemon=True)
        self._thread.start()

    def on_stop(self) -> None:
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def snapshot(self) -> ResourceSnapshot:
        gpu_percent, gpu_memory_used_mb, gpu_memory_total_mb = self._gpu_values()
        self._last_snapshot = ResourceSnapshot(
            cpu_percent=self._cpu_percent(),
            ram_used_mb=self._ram_used_mb(),
            ram_total_mb=self._ram_total_mb(),
            disk_used_gb=self._disk_used_gb(),
            disk_total_gb=self._disk_total_gb(),
            network_received_mb=self._network_bytes(index=0),
            network_sent_mb=self._network_bytes(index=1),
            gpu_percent=gpu_percent,
            gpu_memory_used_mb=gpu_memory_used_mb,
            gpu_memory_total_mb=gpu_memory_total_mb,
        )
        return self._last_snapshot

    def latest(self) -> ResourceSnapshot:
        return self._last_snapshot

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=True,
            detail="Resource snapshots available",
        )

    def _loop(self) -> None:
        while not self._stopping.is_set():
            snapshot = self.snapshot()
            if self.context is not None:
                self.context.event_bus.publish("resources.snapshot", snapshot.__dict__, source=self.name)
            self._stopping.wait(self.interval_seconds)

    def _cpu_percent(self) -> float | None:
        if self._cpu_sampler is None:
            return None
        try:
            return self._cpu_sampler.sample()
        except Exception:
            return None

    def _memory_status(self) -> _MemoryStatus | None:
        if not hasattr(ctypes, "windll"):
            return None
        status = _MemoryStatus()
        status.dwLength = ctypes.sizeof(_MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):  # type: ignore[attr-defined]
            return status
        return None

    def _ram_total_mb(self) -> int | None:
        status = self._memory_status()
        if status is None:
            return None
        return int(status.ullTotalPhys / 1024 / 1024)

    def _ram_used_mb(self) -> int | None:
        status = self._memory_status()
        if status is None:
            return None
        return int((status.ullTotalPhys - status.ullAvailPhys) / 1024 / 1024)

    def _disk_usage(self):
        anchor = Path(self.project_root.anchor or self.project_root)
        return shutil.disk_usage(anchor)

    def _disk_total_gb(self) -> float:
        return round(self._disk_usage().total / 1024 / 1024 / 1024, 2)

    def _disk_used_gb(self) -> float:
        usage = self._disk_usage()
        return round((usage.total - usage.free) / 1024 / 1024 / 1024, 2)

    def _network_bytes(self, index: int) -> float | None:
        try:
            result = subprocess.run(["netstat", "-e"], capture_output=True, text=True, timeout=3, check=False)
        except OSError:
            return None
        if result.returncode != 0:
            return None
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts and parts[0].lower() == "bytes" and len(parts) >= 3:
                value = parts[1 + index]
                if value.isdigit():
                    return round(int(value) / 1024 / 1024, 2)
        return None

    def _gpu_values(self) -> tuple[float | None, int | None, int | None]:
        nvidia_smi = shutil.which("nvidia-smi")
        if not nvidia_smi:
            return (None, None, None)
        try:
            result = subprocess.run(
                [
                    nvidia_smi,
                    "--query-gpu=utilization.gpu,memory.used,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except OSError:
            return (None, None, None)
        if result.returncode != 0 or not result.stdout.strip():
            return (None, None, None)
        parts = [part.strip() for part in result.stdout.splitlines()[0].split(",")]
        if len(parts) < 3:
            return (None, None, None)
        try:
            return (float(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return (None, None, None)
