from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime


class HelloTerryPlugin:
    def commands(self) -> Mapping[str, Callable[..., str]]:
        return {
            "hello": self.hello,
            "utc_time": self.utc_time,
        }

    def hello(self, name: str = "Terry") -> str:
        return f"Hello, {name}. The TerryGPT plugin system is working."

    def utc_time(self) -> str:
        return datetime.now(UTC).isoformat()


def create_plugin() -> HelloTerryPlugin:
    return HelloTerryPlugin()

