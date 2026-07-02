from __future__ import annotations

import heapq
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from terrygpt.core.module import BaseModule, ModuleHealth
from terrygpt.core.module import ModuleState
from terrygpt.database.manager import DatabaseManager, new_id, utc_now


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ProgressCallback = Callable[[int, str], None]
TaskHandler = Callable[[dict[str, Any], ProgressCallback, threading.Event], dict[str, Any]]


@dataclass(order=True)
class QueueItem:
    priority: int
    created_order: int
    task_id: str = field(compare=False)


@dataclass
class ScheduledTask:
    id: str
    title: str
    payload: dict[str, Any]
    priority: int
    max_retries: int
    retries: int = 0
    progress: int = 0
    status: TaskStatus = TaskStatus.QUEUED
    result: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event, repr=False)


class TaskScheduler(BaseModule):
    def __init__(self) -> None:
        super().__init__(name="task_scheduler", dependencies=("database",))
        self._handlers: dict[str, TaskHandler] = {}
        self._tasks: dict[str, ScheduledTask] = {}
        self._queue: list[QueueItem] = []
        self._condition = threading.Condition()
        self._worker: threading.Thread | None = None
        self._stopping = False
        self._counter = 0

    def on_start(self) -> None:
        self._stopping = False
        self._worker = threading.Thread(target=self._work_loop, name="TerryGPTTaskScheduler", daemon=True)
        self._worker.start()

    def on_stop(self) -> None:
        with self._condition:
            self._stopping = True
            self._condition.notify_all()
        if self._worker is not None:
            self._worker.join(timeout=5)

    def register_handler(self, task_type: str, handler: TaskHandler) -> None:
        self._handlers[task_type] = handler

    def submit(self, title: str, task_type: str, payload: dict[str, Any] | None = None, priority: int = 100, max_retries: int = 0) -> str:
        task_id = new_id()
        task_payload = dict(payload or {})
        task_payload["task_type"] = task_type
        task = ScheduledTask(id=task_id, title=title, payload=task_payload, priority=priority, max_retries=max_retries)
        with self._condition:
            self._tasks[task_id] = task
            self._counter += 1
            heapq.heappush(self._queue, QueueItem(priority=priority, created_order=self._counter, task_id=task_id))
            self._persist(task)
            self._condition.notify()
        self._publish("task.queued", task)
        return task_id

    def cancel(self, task_id: str) -> None:
        task = self._tasks[task_id]
        task.cancel_event.set()
        task.status = TaskStatus.CANCELLED
        self._persist(task)
        self._publish("task.cancelled", task)

    def get(self, task_id: str) -> ScheduledTask:
        return self._tasks[task_id]

    def list_tasks(self) -> list[ScheduledTask]:
        return list(self._tasks.values())

    def health(self) -> ModuleHealth:
        return ModuleHealth(
            name=self.name,
            state=self.state,
            healthy=self._worker is not None and self._worker.is_alive() if self.state == ModuleState.STARTED else True,
            detail=f"{len(self._tasks)} task(s) tracked",
        )

    def _work_loop(self) -> None:
        while True:
            with self._condition:
                while not self._queue and not self._stopping:
                    self._condition.wait(timeout=0.5)
                if self._stopping:
                    return
                item = heapq.heappop(self._queue)
                task = self._tasks[item.task_id]
            if task.status == TaskStatus.CANCELLED:
                continue
            self._run_task(task)

    def _run_task(self, task: ScheduledTask) -> None:
        task_type = str(task.payload.get("task_type", ""))
        handler = self._handlers.get(task_type)
        if handler is None:
            task.status = TaskStatus.FAILED
            task.error = f"No task handler registered for {task_type}"
            self._persist(task)
            self._publish("task.failed", task)
            return

        task.status = TaskStatus.RUNNING
        task.progress = 0
        self._persist(task)
        self._publish("task.started", task)

        try:
            result = handler(task.payload, lambda value, message: self._progress(task, value, message), task.cancel_event)
            if task.cancel_event.is_set():
                task.status = TaskStatus.CANCELLED
            else:
                task.status = TaskStatus.COMPLETED
                task.progress = 100
                task.result = result
        except Exception as exc:
            task.retries += 1
            task.error = str(exc)
            if task.retries <= task.max_retries and not task.cancel_event.is_set():
                task.status = TaskStatus.QUEUED
                with self._condition:
                    self._counter += 1
                    heapq.heappush(self._queue, QueueItem(task.priority, self._counter, task.id))
                    self._condition.notify()
            else:
                task.status = TaskStatus.FAILED
        self._persist(task)
        self._publish(f"task.{task.status}", task)

    def _progress(self, task: ScheduledTask, value: int, message: str) -> None:
        task.progress = max(0, min(100, value))
        self._persist(task)
        if self.context is not None:
            self.context.event_bus.publish(
                "task.progress",
                {"id": task.id, "progress": task.progress, "message": message},
                source=self.name,
            )

    def _persist(self, task: ScheduledTask) -> None:
        if self.context is None or self.context.core is None:
            return
        database = self.context.core.module("database")
        if not isinstance(database, DatabaseManager):
            return
        timestamp = utc_now()
        with database.connect() as connection:
            existing = connection.execute("SELECT id, created_at FROM tasks WHERE id = ?", (task.id,)).fetchone()
            created_at = str(existing["created_at"]) if existing else timestamp
            connection.execute(
                """
                INSERT INTO tasks
                    (id, title, status, priority, progress, retries, max_retries, payload_json, result_json, error, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    progress = excluded.progress,
                    retries = excluded.retries,
                    result_json = excluded.result_json,
                    error = excluded.error,
                    updated_at = excluded.updated_at
                """,
                (
                    task.id,
                    task.title,
                    task.status,
                    task.priority,
                    task.progress,
                    task.retries,
                    task.max_retries,
                    json.dumps(task.payload, sort_keys=True),
                    json.dumps(task.result, sort_keys=True),
                    task.error,
                    created_at,
                    timestamp,
                ),
            )

    def _publish(self, event_type: str, task: ScheduledTask) -> None:
        if self.context is not None:
            self.context.event_bus.publish(
                event_type,
                {"id": task.id, "title": task.title, "status": task.status, "progress": task.progress},
                source=self.name,
            )
