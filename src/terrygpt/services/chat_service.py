from __future__ import annotations

import logging
from typing import Iterable

from terrygpt.config import OllamaSettings
from terrygpt.database import TerryDatabase
from terrygpt.models import Conversation
from terrygpt.services.memory_service import MemoryService
from terrygpt.services.ollama import OllamaClient, OllamaError

LOGGER = logging.getLogger(__name__)


class ChatService:
    def __init__(self, database: TerryDatabase, memory: MemoryService, ollama: OllamaClient, settings: OllamaSettings) -> None:
        self.database = database
        self.memory = memory
        self.ollama = ollama
        self.settings = settings

    def start_conversation(self, title: str | None = None) -> Conversation:
        clean_title = (title or "New chat").strip() or "New chat"
        return self.database.create_conversation(clean_title[:120])

    def _select_model(self, requested_model: str | None) -> str:
        if requested_model and requested_model.strip():
            return requested_model.strip()
        if self.settings.default_model.strip():
            return self.settings.default_model.strip()
        models = self.ollama.list_models()
        if not models:
            raise OllamaError("Ollama is running, but it did not report any installed models.")
        return models[0].name

    def stream_reply(self, conversation_id: str, user_text: str, model: str | None = None) -> Iterable[str]:
        clean_text = user_text.strip()
        if not clean_text:
            raise ValueError("Message cannot be empty.")

        self.database.add_message(conversation_id=conversation_id, role="user", content=clean_text)
        messages = self.database.list_messages(conversation_id)
        selected_model = self._select_model(model)
        LOGGER.info("Starting Ollama response with model %s", selected_model)

        chunks: list[str] = []
        for chunk in self.ollama.stream_chat(model=selected_model, messages=messages):
            chunks.append(chunk)
            yield chunk

        assistant_text = "".join(chunks).strip()
        self.database.add_message(conversation_id=conversation_id, role="assistant", content=assistant_text)
        self.memory.remember(
            kind="conversation",
            content=f"User: {clean_text}\nAssistant: {assistant_text}",
            metadata={"conversation_id": conversation_id, "model": selected_model},
        )

    def complete_reply(self, conversation_id: str, user_text: str, model: str | None = None) -> str:
        return "".join(self.stream_reply(conversation_id=conversation_id, user_text=user_text, model=model))

