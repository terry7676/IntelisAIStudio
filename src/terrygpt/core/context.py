from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from terrygpt.config import TerryConfig
from terrygpt.core.events import EventBus

if TYPE_CHECKING:
    from terrygpt.logging.manager import LogManager


@dataclass
class CoreContext:
    config: TerryConfig
    event_bus: EventBus
    log_manager: "LogManager | None" = None
    core: object | None = None
