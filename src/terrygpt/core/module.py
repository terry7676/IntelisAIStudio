from __future__ import annotations

import traceback
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from terrygpt.core.context import CoreContext


class ModuleState(StrEnum):
    CREATED = "created"
    INITIALIZED = "initialized"
    STARTED = "started"
    STOPPED = "stopped"
    FAILED = "failed"


@dataclass(frozen=True)
class ModuleHealth:
    name: str
    state: ModuleState
    healthy: bool
    detail: str = ""


class BaseModule:
    def __init__(self, name: str, dependencies: tuple[str, ...] = ()) -> None:
        self.name = name
        self.dependencies = dependencies
        self.state = ModuleState.CREATED
        self.context: CoreContext | None = None
        self.last_error = ""

    def attach(self, context: "CoreContext") -> None:
        self.context = context

    def initialize(self) -> None:
        self._run_lifecycle("initialize", self.on_initialize, ModuleState.INITIALIZED)

    def start(self) -> None:
        self._run_lifecycle("start", self.on_start, ModuleState.STARTED)

    def stop(self) -> None:
        self._run_lifecycle("stop", self.on_stop, ModuleState.STOPPED)

    def restart(self) -> None:
        self.stop()
        self.start()

    def on_initialize(self) -> None:
        return None

    def on_start(self) -> None:
        return None

    def on_stop(self) -> None:
        return None

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=self.state != ModuleState.FAILED,
            detail=self.last_error,
        )

    def _run_lifecycle(self, action: str, callback, success_state: ModuleState) -> None:
        try:
            callback()
            self.last_error = ""
            self.state = success_state
            if self.context is not None:
                self.context.event_bus.publish(
                    f"module.{action}",
                    {"module": self.name, "state": self.state},
                    source=self.name,
                )
        except Exception as exc:
            self.state = ModuleState.FAILED
            self.last_error = "".join(traceback.format_exception_only(type(exc), exc)).strip()
            if self.context is not None:
                self.context.event_bus.publish(
                    "module.failed",
                    {"module": self.name, "action": action, "error": self.last_error},
                    source=self.name,
                )
            raise

