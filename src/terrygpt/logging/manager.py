from __future__ import annotations

import logging as py_logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from terrygpt.config import TerryConfig
from terrygpt.core.module import BaseModule, ModuleHealth


LOG_CATEGORIES = ("application", "errors", "ai", "plugins", "security", "automation", "api")


class LogManager(BaseModule):
    def __init__(self, config: TerryConfig) -> None:
        super().__init__(name="logging")
        self.config = config
        self.log_directory = config.logging.path.parent
        self._loggers: dict[str, py_logging.Logger] = {}

    def on_initialize(self) -> None:
        self.log_directory.mkdir(parents=True, exist_ok=True)
        formatter = py_logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        for category in LOG_CATEGORIES:
            logger = py_logging.getLogger(f"terrygpt.{category}")
            logger.setLevel(getattr(py_logging, self.config.logging.level, py_logging.INFO))
            logger.propagate = False
            logger.handlers.clear()

            path = self.log_directory / f"{category}.log"
            handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            self._loggers[category] = logger

        root = py_logging.getLogger()
        root.setLevel(getattr(py_logging, self.config.logging.level, py_logging.INFO))
        root.handlers.clear()
        root.addHandler(self._loggers["application"].handlers[0])

    def on_start(self) -> None:
        if self.context is not None:
            self.context.event_bus.subscribe("*", self._log_event)

    def on_stop(self) -> None:
        seen_handlers = set()
        for logger in self._loggers.values():
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                if id(handler) not in seen_handlers:
                    seen_handlers.add(id(handler))
                    handler.close()
        root = py_logging.getLogger()
        for handler in list(root.handlers):
            root.removeHandler(handler)
            if id(handler) not in seen_handlers:
                seen_handlers.add(id(handler))
                handler.close()

    def get_logger(self, category: str) -> py_logging.Logger:
        return self._loggers.get(category, self._loggers.get("application", py_logging.getLogger("terrygpt.application")))

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=all((self.log_directory / f"{category}.log").exists() for category in LOG_CATEGORIES),
            detail=f"Logs at {self.log_directory}",
        )

    def _log_event(self, event: object) -> None:
        event_type = str(getattr(event, "event_type", "unknown"))
        if event_type.startswith("security."):
            category = "security"
        elif event_type.startswith("plugin."):
            category = "plugins"
        elif event_type.startswith("api."):
            category = "api"
        elif event_type.startswith("ai."):
            category = "ai"
        elif event_type.startswith("task.") or event_type.startswith("automation."):
            category = "automation"
        elif event_type.endswith(".failed"):
            category = "errors"
        else:
            category = "application"
        self.get_logger(category).info("%s %s", event_type, getattr(event, "payload", {}))
