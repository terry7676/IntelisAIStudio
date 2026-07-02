from __future__ import annotations

import logging
from pathlib import Path

from terrygpt.ai.providers import AIProviderRegistry, OllamaProvider
from terrygpt.app.dependencies import DependencyChecker
from terrygpt.brain.manager import AIManager
from terrygpt.config import load_config
from terrygpt.configuration.manager import ConfigurationManager
from terrygpt.core.context import CoreContext
from terrygpt.core.events import EventBus
from terrygpt.core.module import BaseModule, ModuleHealth, ModuleState
from terrygpt.database.manager import DatabaseManager
from terrygpt.logging.manager import LogManager
from terrygpt.memory.engine import MemoryEngine
from terrygpt.plugins.loader import PluginLoader
from terrygpt.resources.monitor import ResourceMonitor
from terrygpt.security.manager import SecurityManager
from terrygpt.tasks.scheduler import TaskScheduler


class CoreManager:
    def __init__(self, context: CoreContext) -> None:
        self.context = context
        self._modules: dict[str, BaseModule] = {}
        self._restart_attempts: dict[str, int] = {}
        self._logger = logging.getLogger("terrygpt.core")

    @classmethod
    def build(cls, config_path: Path | None = None) -> "CoreManager":
        config = load_config(config_path=config_path)
        log_manager = LogManager(config)
        log_manager.initialize()

        event_bus = EventBus(logger=log_manager.get_logger("application"))
        context = CoreContext(config=config, event_bus=event_bus, log_manager=log_manager)
        manager = cls(context)
        context.core = manager
        manager.register(log_manager)

        database = DatabaseManager(config.database.path)
        configuration = ConfigurationManager(config.project_root)
        dependencies = DependencyChecker(config.project_root)
        ai_registry = AIProviderRegistry()
        ai_registry.register_provider(OllamaProvider(config.ollama.base_url, config.ollama.request_timeout_seconds))

        manager.register(database)
        manager.register(configuration)
        manager.register(dependencies)
        manager.register(SecurityManager())
        manager.register(ai_registry)
        manager.register(MemoryEngine())
        manager.register(AIManager())
        manager.register(PluginLoader(config.plugins.directory))
        manager.register(TaskScheduler())
        manager.register(ResourceMonitor(config.project_root))
        return manager

    def register(self, module: BaseModule) -> None:
        if module.name in self._modules:
            raise ValueError(f"Module already registered: {module.name}")
        module.attach(self.context)
        self._modules[module.name] = module

    def module(self, name: str) -> BaseModule:
        try:
            return self._modules[name]
        except KeyError as exc:
            raise KeyError(f"Unknown module: {name}") from exc

    def modules(self) -> list[BaseModule]:
        return list(self._modules.values())

    def initialize(self) -> None:
        self.context.event_bus.publish("core.initialize.started", source="core")
        for module in self.modules():
            if module.state == ModuleState.CREATED:
                self._safe_lifecycle(module, "initialize")
        self.context.event_bus.publish("core.initialize.completed", source="core")

    def start(self) -> None:
        self.context.event_bus.publish("core.start.started", source="core")
        for module in self.modules():
            if module.state in {ModuleState.INITIALIZED, ModuleState.STOPPED}:
                self._safe_lifecycle(module, "start")
        self.context.event_bus.publish("core.start.completed", source="core")

    def stop(self) -> None:
        self.context.event_bus.publish("core.stop.started", source="core")
        for module in reversed(self.modules()):
            if module.state == ModuleState.STARTED:
                self._safe_lifecycle(module, "stop")
        self.context.event_bus.publish("core.stop.completed", source="core")

    def restart_module(self, name: str) -> None:
        module = self.module(name)
        self.context.event_bus.publish("module.restart.requested", {"module": name}, source="core")
        self._safe_lifecycle(module, "restart")

    def monitor_once(self) -> list[ModuleHealth]:
        health = [module.health() for module in self.modules()]
        for item in health:
            if not item.healthy and self._restart_attempts.get(item.name, 0) < 1:
                self._restart_attempts[item.name] = self._restart_attempts.get(item.name, 0) + 1
                self.context.event_bus.publish(
                    "module.recovery.attempted",
                    {"module": item.name, "detail": item.detail},
                    source="core",
                )
                self.restart_module(item.name)
        return health

    def health_report(self) -> list[ModuleHealth]:
        return [module.health() for module in self.modules()]

    def _safe_lifecycle(self, module: BaseModule, action: str) -> None:
        try:
            getattr(module, action)()
        except Exception as exc:
            self._logger.exception("Module %s failed during %s", module.name, action)
            self.context.event_bus.publish(
                "notification.created",
                {"level": "error", "message": f"{module.name} failed during {action}: {exc}"},
                source="core",
            )
