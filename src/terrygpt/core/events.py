from __future__ import annotations

import logging
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


EventHandler = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    event_type: str
    source: str
    payload: dict[str, Any] = field(default_factory=dict)
    correlation_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


@dataclass(frozen=True)
class EventSubscription:
    event_type: str
    handler: EventHandler


class EventBus:
    def __init__(self, logger: logging.Logger | None = None, history_limit: int = 500) -> None:
        self._logger = logger or logging.getLogger("terrygpt.events")
        self._history: deque[Event] = deque(maxlen=history_limit)
        self._dead_letters: deque[tuple[Event, str]] = deque(maxlen=100)
        self._subscriptions: dict[str, list[EventHandler]] = {}
        self._lock = threading.RLock()

    def subscribe(self, event_type: str, handler: EventHandler) -> EventSubscription:
        with self._lock:
            self._subscriptions.setdefault(event_type, []).append(handler)
        return EventSubscription(event_type=event_type, handler=handler)

    def unsubscribe(self, subscription: EventSubscription) -> None:
        with self._lock:
            handlers = self._subscriptions.get(subscription.event_type, [])
            if subscription.handler in handlers:
                handlers.remove(subscription.handler)

    def publish(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        source: str = "core",
        correlation_id: str | None = None,
    ) -> Event:
        event = Event(
            event_type=event_type,
            source=source,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        self.publish_event(event)
        return event

    def publish_event(self, event: Event) -> None:
        with self._lock:
            self._history.append(event)
            handlers = list(self._subscriptions.get(event.event_type, []))
            handlers.extend(self._subscriptions.get("*", []))

        for handler in handlers:
            try:
                handler(event)
            except Exception as exc:
                message = f"{handler!r} failed for event {event.event_type}: {exc}"
                self._dead_letters.append((event, message))
                self._logger.exception(message)

    def history(self, limit: int = 100) -> list[Event]:
        with self._lock:
            return list(self._history)[-limit:]

    def dead_letters(self) -> list[tuple[Event, str]]:
        with self._lock:
            return list(self._dead_letters)

