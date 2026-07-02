from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.ai.providers import AIProviderRegistry, ProviderChunk, ProviderHealth, ProviderMessage, ProviderModelInfo
from terrygpt.configuration.manager import ConfigurationManager
from terrygpt.core.context import CoreContext
from terrygpt.core.events import EventBus
from terrygpt.core.manager import CoreManager
from terrygpt.database.manager import DatabaseManager
from terrygpt.memory.engine import MemoryEngine


class FakeProvider:
    name = "fake"

    def __init__(self, chunks: tuple[str, ...] = ("Hello", " Terry")) -> None:
        self.chunks = chunks

    def health(self) -> ProviderHealth:
        return ProviderHealth(self.name, True, "fake provider ready")

    def list_models(self) -> list[str]:
        return ["fake-model"]

    def model_details(self) -> list[ProviderModelInfo]:
        return [
            ProviderModelInfo(
                provider_name=self.name,
                model_name="fake-model",
                parameter_size="1B",
                size_bytes=1024,
                quantization="Q4",
                context_length=4096,
                metadata={},
            )
        ]

    def stream_chat(self, model: str, messages: list[ProviderMessage], options: dict[str, object]):
        for chunk in self.chunks:
            yield ProviderChunk(content=chunk)
        yield ProviderChunk(content="", done=True, prompt_tokens=10, completion_tokens=3, total_duration_ms=25)


def build_test_core():
    temp = tempfile.TemporaryDirectory()
    root = Path(temp.name)
    context = CoreContext(config=None, event_bus=EventBus())  # type: ignore[arg-type]
    core = CoreManager(context)
    context.core = core

    database = DatabaseManager(root / "data" / "test.sqlite")
    configuration = ConfigurationManager(root)
    providers = AIProviderRegistry()
    providers.register_provider(FakeProvider())
    memory = MemoryEngine()

    core.register(database)
    core.register(configuration)
    core.register(providers)
    core.register(memory)
    return temp, core

