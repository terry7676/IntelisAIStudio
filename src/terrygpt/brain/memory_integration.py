from __future__ import annotations

import hashlib
import re

from terrygpt.brain.conversation_manager import ConversationManager
from terrygpt.memory.engine import MemoryEngine


TRIVIAL_RE = re.compile(r"^(hi|hello|hey|ok|okay|thanks|thank you|yes|no|cool)[.! ]*$", re.IGNORECASE)


class BrainMemoryIntegration:
    def __init__(self, conversations: ConversationManager, memory: MemoryEngine) -> None:
        self.conversations = conversations
        self.memory = memory

    def update_after_response(self, conversation_id: str, user_message: str, assistant_message: str, model_name: str) -> None:
        importance = self.score_importance(user_message, assistant_message)
        if importance < 45:
            return
        content = f"User: {user_message.strip()}\nAssistant: {assistant_message.strip()}"
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = self.memory.search(digest, limit=1, include_expired=True)
        if existing:
            return
        self.memory.remember(
            memory_type="conversation",
            content=f"{digest}\n{content}",
            importance=importance,
            summary=self.memory.summarize(content),
            metadata={"conversation_id": conversation_id, "model": model_name, "digest": digest},
        )
        self._summarize_if_needed(conversation_id)

    def score_importance(self, user_message: str, assistant_message: str) -> int:
        text = f"{user_message} {assistant_message}".strip()
        if not text or TRIVIAL_RE.match(user_message.strip()):
            return 0
        score = 35
        lower = text.lower()
        for marker in ("remember", "prefer", "important", "project", "setting", "always", "never"):
            if marker in lower:
                score += 15
        if len(text) > 500:
            score += 10
        return max(0, min(100, score))

    def _summarize_if_needed(self, conversation_id: str) -> None:
        messages = self.conversations.messages(conversation_id)
        if len(messages) < 12:
            return
        user_points = [message.content for message in messages if message.role == "user"][-6:]
        summary = self.memory.summarize(" | ".join(user_points), max_chars=500)
        self.conversations.update_summary(conversation_id, summary)

