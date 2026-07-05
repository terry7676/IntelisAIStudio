from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Any

from terrygpt.ai.providers import AIProviderRegistry
from terrygpt.brain.context_builder import ContextBuilder
from terrygpt.brain.conversation_manager import ConversationManager
from terrygpt.brain.memory_integration import BrainMemoryIntegration
from terrygpt.brain.model_manager import ModelManager
from terrygpt.brain.models import BrainSettings, ResponseChunk
from terrygpt.brain.prompt_manager import PromptManager
from terrygpt.brain.task_router import TaskRouter, TaskType
from terrygpt.configuration.manager import ConfigurationManager
from terrygpt.core.module import BaseModule, ModuleHealth
from terrygpt.database.manager import DatabaseManager, new_id, utc_now
from terrygpt.media.manager import MediaManager
from terrygpt.memory.engine import MemoryEngine


class AIManager(BaseModule):
    def __init__(self) -> None:
        super().__init__(
            name="ai_manager",
            dependencies=("database", "configuration", "ai_provider_registry", "memory_engine"),
        )
        self.database: DatabaseManager | None = None
        self.configuration: ConfigurationManager | None = None
        self.providers: AIProviderRegistry | None = None
        self.memory: MemoryEngine | None = None
        self.conversations: ConversationManager | None = None
        self.prompts: PromptManager | None = None
        self.models: ModelManager | None = None
        self.context_builder: ContextBuilder | None = None
        self.memory_integration: BrainMemoryIntegration | None = None
        self._settings_cache: BrainSettings | None = None
        self.task_router = TaskRouter()

    def on_initialize(self) -> None:
        self.database = self._module("database", DatabaseManager)
        self.configuration = self._module("configuration", ConfigurationManager)
        self.providers = self._module("ai_provider_registry", AIProviderRegistry)
        self.memory = self._module("memory_engine", MemoryEngine)

        self.conversations = ConversationManager(self.database)
        self.prompts = PromptManager(self.database)
        self.models = ModelManager(self.database, self.providers)
        self.context_builder = ContextBuilder(self.conversations, self.prompts, self.memory, self.configuration)
        self.memory_integration = BrainMemoryIntegration(self.conversations, self.memory)

        self.prompts.ensure_defaults(self.settings().system_prompt)
        self.refresh_models()
        if self.context is not None:
            self.context.event_bus.subscribe("ai.requested", self._handle_ai_requested)

    def settings(self) -> BrainSettings:
        if self._settings_cache is not None:
            return self._settings_cache
        config = self._configuration()
        ai = config.get_category("ai")
        self._settings_cache = BrainSettings(
            provider_name=str(ai.get("provider_name", ai.get("default_provider", "ollama"))),
            default_model=str(ai.get("default_model", "")),
            temperature=float(ai.get("temperature", 0.7)),
            top_p=float(ai.get("top_p", 0.9)),
            maximum_tokens=int(ai.get("maximum_tokens", 2048)),
            streaming_enabled=bool(ai.get("streaming_enabled", True)),
            memory_enabled=bool(ai.get("memory_enabled", True)),
            system_prompt=str(ai.get("system_prompt", BrainSettings().system_prompt)),
        )
        return self._settings_cache

    def update_settings(self, **kwargs: Any) -> BrainSettings:
        valid_keys = set(BrainSettings.__dataclass_fields__)
        invalid = set(kwargs) - valid_keys
        if invalid:
            raise ValueError(f"Unknown AI setting(s): {', '.join(sorted(invalid))}")
        config = self._configuration()
        for key, value in kwargs.items():
            config.set("ai", "default_provider" if key == "provider_name" else key, value)
        self._settings_cache = None
        return self.settings()

    def create_conversation(self, title: str = "New chat") -> str:
        settings = self.settings()
        model = self._select_model(settings)
        record = self._conversations().create(
            title=title,
            provider_name=settings.provider_name,
            model_name=model.model_name if model is not None else settings.default_model,
        )
        return record.id

    def list_conversations(self, include_archived: bool = False):
        return self._conversations().list(include_archived=include_archived)

    def rename_conversation(self, conversation_id: str, title: str):
        return self._conversations().rename(conversation_id, title)

    def archive_conversation(self, conversation_id: str):
        return self._conversations().archive(conversation_id)

    def restore_conversation(self, conversation_id: str):
        return self._conversations().restore(conversation_id)

    def delete_conversation(self, conversation_id: str) -> None:
        self._conversations().delete(conversation_id)

    def search_conversations(self, query: str):
        return self._conversations().search(query)

    def messages(self, conversation_id: str):
        return self._conversations().messages(conversation_id)

    def refresh_models(self):
        models = self._models().refresh()
        if self.context is not None:
            self.context.event_bus.publish(
                "ai.models.refreshed",
                {"count": len(models), "models": [model.model_name for model in models]},
                source=self.name,
            )
        return models

    def list_models(self):
        return self._models().list()

    def stream_response(self, conversation_id: str | None, user_message: str) -> Iterable[ResponseChunk]:
        request_id = new_id()
        started = time.perf_counter()
        settings = self.settings()
        task = self.task_router.detect(user_message)
        if task == TaskType.IMAGE:
            active_conversation_id = conversation_id or self.create_conversation(user_message[:80])
            conversations = self._conversations()
            conversations.add_message(active_conversation_id, "user", user_message)
            try:
                result = self._media_manager().generate_image(user_message)
                message = f"Image generated and saved to {result.output_path}"
                conversations.add_message(
                    active_conversation_id,
                    "assistant",
                    message,
                    metadata={"image_path": str(result.output_path), "provider": result.provider_name},
                )
                yield ResponseChunk(
                    content=message,
                    done=True,
                    conversation_id=active_conversation_id,
                    request_id=request_id,
                )
            except Exception as exc:
                error = str(exc)
                self._notify_failure(error)
                yield ResponseChunk("", True, active_conversation_id, request_id, error=error)
            return
        model = self._select_model(settings)
        if model is None:
            error = "No AI model is available. Install an Ollama model and refresh models."
            self._notify_failure(error)
            yield ResponseChunk("", True, conversation_id or "", request_id, error=error)
            return

        active_conversation_id = conversation_id or self.create_conversation(user_message[:80])
        conversations = self._conversations()
        user_record = conversations.add_message(active_conversation_id, "user", user_message)
        context = self._context_builder().build(active_conversation_id, user_record.content, settings)
        provider = self._providers().provider(model.provider_name)
        options = {
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "num_predict": settings.maximum_tokens,
        }

        assistant_parts: list[str] = []
        prompt_tokens = context.prompt_tokens_estimate
        completion_tokens = 0
        final_duration_ms = 0
        status = "completed"
        error = ""

        self._publish_ai_event("ai.request.started", {"request_id": request_id, "model": model.model_name})
        try:
            for provider_chunk in provider.stream_chat(model.model_name, context.messages, options):
                if provider_chunk.content:
                    assistant_parts.append(provider_chunk.content)
                    yield ResponseChunk(
                        content=provider_chunk.content,
                        done=False,
                        conversation_id=active_conversation_id,
                        request_id=request_id,
                    )
                if provider_chunk.prompt_tokens:
                    prompt_tokens = provider_chunk.prompt_tokens
                if provider_chunk.completion_tokens:
                    completion_tokens = provider_chunk.completion_tokens
                if provider_chunk.total_duration_ms:
                    final_duration_ms = provider_chunk.total_duration_ms
        except Exception as exc:
            status = "failed"
            error = str(exc)
            self._notify_failure(error)
            self._record_request(
                request_id,
                active_conversation_id,
                model.provider_name,
                model.model_name,
                prompt_tokens,
                completion_tokens,
                int((time.perf_counter() - started) * 1000),
                status,
                error,
            )
            yield ResponseChunk("", True, active_conversation_id, request_id, prompt_tokens, completion_tokens, error=error)
            return

        assistant_text = "".join(assistant_parts).strip()
        checked_text = self._safety_check(assistant_text)
        if checked_text:
            conversations.add_message(
                active_conversation_id,
                "assistant",
                checked_text,
                metadata={"request_id": request_id, "model": model.model_name, "provider": model.provider_name},
            )
            if self._memory_integration() is not None:
                self._memory_integration().update_after_response(
                    active_conversation_id,
                    user_record.content,
                    checked_text,
                    model.model_name,
                )
        if completion_tokens == 0:
            completion_tokens = conversations.estimate_tokens(checked_text)
        response_time_ms = final_duration_ms or int((time.perf_counter() - started) * 1000)
        self._record_request(
            request_id,
            active_conversation_id,
            model.provider_name,
            model.model_name,
            prompt_tokens,
            completion_tokens,
            response_time_ms,
            status,
            error,
        )
        self._publish_ai_event(
            "ai.request.completed",
            {"request_id": request_id, "conversation_id": active_conversation_id, "response_time_ms": response_time_ms},
        )
        yield ResponseChunk(
            "",
            True,
            active_conversation_id,
            request_id,
            prompt_tokens,
            completion_tokens,
            response_time_ms,
        )

    def complete_response(self, conversation_id: str | None, user_message: str) -> str:
        chunks = []
        for chunk in self.stream_response(conversation_id, user_message):
            if chunk.error:
                raise RuntimeError(chunk.error)
            chunks.append(chunk.content)
        return "".join(chunks)

    def health(self) -> ModuleHealth:
        model_count = len(self._models().list()) if self.models is not None else 0
        return ModuleHealth(self.name, self.state, True, f"AI Brain ready with {model_count} model(s) cached")

    def _record_request(
        self,
        request_id: str,
        conversation_id: str,
        provider_name: str,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        response_time_ms: int,
        status: str,
        error: str,
    ) -> None:
        total_tokens = prompt_tokens + completion_tokens
        timestamp = utc_now()
        database = self._database()
        with database.connect() as connection:
            connection.execute(
                """
                INSERT INTO ai_request_logs
                    (id, conversation_id, provider_name, model_name, prompt_tokens, completion_tokens,
                     total_tokens, response_time_ms, status, error, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    request_id,
                    conversation_id,
                    provider_name,
                    model_name,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    response_time_ms,
                    status,
                    error,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO token_usage
                    (id, conversation_id, provider_name, model_name, prompt_tokens, completion_tokens, total_tokens, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (new_id(), conversation_id, provider_name, model_name, prompt_tokens, completion_tokens, total_tokens, timestamp),
            )

    def _select_model(self, settings: BrainSettings):
        return self._models().choose(settings.provider_name, settings.default_model or None)

    def _safety_check(self, response: str) -> str:
        return response.strip()

    def _notify_failure(self, error: str) -> None:
        self._publish_ai_event("ai.request.failed", {"error": error})
        if self.context is not None:
            self.context.event_bus.publish(
                "notification.created",
                {"level": "error", "message": f"AI provider failed: {error}"},
                source=self.name,
            )
        try:
            self._providers().refresh_health()
        except Exception:
            pass

    def _handle_ai_requested(self, event: object) -> None:
        payload = getattr(event, "payload", {})
        conversation_id = payload.get("conversation_id")
        message = str(payload.get("message", ""))
        if message:
            for _chunk in self.stream_response(conversation_id if isinstance(conversation_id, str) else None, message):
                pass

    def _publish_ai_event(self, event_type: str, payload: dict[str, Any]) -> None:
        if self.context is not None:
            self.context.event_bus.publish(event_type, payload, source=self.name)

    def _module(self, name: str, expected_type):
        if self.context is None or self.context.core is None:
            raise RuntimeError("AIManager requires CoreManager access.")
        module = self.context.core.module(name)
        if not isinstance(module, expected_type):
            raise RuntimeError(f"Registered {name} module is invalid.")
        return module

    def _database(self) -> DatabaseManager:
        if self.database is None:
            self.database = self._module("database", DatabaseManager)
        return self.database

    def _configuration(self) -> ConfigurationManager:
        if self.configuration is None:
            self.configuration = self._module("configuration", ConfigurationManager)
        return self.configuration

    def _providers(self) -> AIProviderRegistry:
        if self.providers is None:
            self.providers = self._module("ai_provider_registry", AIProviderRegistry)
        return self.providers

    def _models(self) -> ModelManager:
        if self.models is None:
            self.models = ModelManager(self._database(), self._providers())
        return self.models

    def _conversations(self) -> ConversationManager:
        if self.conversations is None:
            self.conversations = ConversationManager(self._database())
        return self.conversations

    def _context_builder(self) -> ContextBuilder:
        if self.context_builder is None:
            self.context_builder = ContextBuilder(
                self._conversations(),
                self._prompts(),
                self._memory(),
                self._configuration(),
            )
        return self.context_builder

    def _prompts(self) -> PromptManager:
        if self.prompts is None:
            self.prompts = PromptManager(self._database())
        return self.prompts

    def _memory(self) -> MemoryEngine:
        if self.memory is None:
            self.memory = self._module("memory_engine", MemoryEngine)
        return self.memory

    def _memory_integration(self) -> BrainMemoryIntegration:
        if self.memory_integration is None:
            self.memory_integration = BrainMemoryIntegration(self._conversations(), self._memory())
        return self.memory_integration

    def _media_manager(self) -> MediaManager:
        return self._module("media_manager", MediaManager)
