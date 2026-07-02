from __future__ import annotations

from terrygpt.ai.providers import ProviderMessage
from terrygpt.brain.conversation_manager import ConversationManager
from terrygpt.brain.models import BrainSettings, BuiltContext
from terrygpt.brain.prompt_manager import PromptManager
from terrygpt.configuration.manager import ConfigurationManager
from terrygpt.memory.engine import MemoryEngine


class ContextBuilder:
    def __init__(
        self,
        conversations: ConversationManager,
        prompts: PromptManager,
        memory: MemoryEngine,
        configuration: ConfigurationManager,
    ) -> None:
        self.conversations = conversations
        self.prompts = prompts
        self.memory = memory
        self.configuration = configuration

    def build(self, conversation_id: str, user_message: str, settings: BrainSettings) -> BuiltContext:
        conversation = self.conversations.get(conversation_id)
        history = self.conversations.messages(conversation_id)
        memories = self.memory.search(user_message, limit=5) if settings.memory_enabled else []
        preferences = self.configuration.get_category("preferences")
        project_context = self._current_project_text()
        document_context = self._loaded_documents_text()

        system_prompt = settings.system_prompt.strip()
        active_prompt = self.prompts.get_active("terrygpt_system")
        if active_prompt is not None:
            system_prompt = active_prompt.template

        context_parts = [
            system_prompt,
            "",
            f"Current conversation title: {conversation.title}",
            f"User preferences: {preferences}",
        ]
        if project_context:
            context_parts.append(f"Current project: {project_context}")
        if memories:
            memory_lines = [f"- {result.item.summary or result.item.content}" for result in memories]
            context_parts.append("Relevant memories:\n" + "\n".join(memory_lines))
        if document_context:
            context_parts.append("Loaded documents:\n" + document_context)

        messages = [ProviderMessage("system", "\n".join(context_parts).strip())]
        messages.extend(
            ProviderMessage(message.role, message.content)
            for message in history[-24:]
            if message.role in {"system", "user", "assistant"}
        )
        if not messages or messages[-1].content != user_message:
            messages.append(ProviderMessage("user", user_message))

        return BuiltContext(
            messages=messages,
            memory_ids=tuple(result.item.id for result in memories),
            prompt_tokens_estimate=sum(self.conversations.estimate_tokens(message.content) for message in messages),
            system_prompt=messages[0].content,
        )

    def _current_project_text(self) -> str:
        row = self.conversations.database.fetch_one(
            "SELECT name, description, path FROM projects WHERE status = 'active' ORDER BY updated_at DESC LIMIT 1"
        )
        if row is None:
            return ""
        return f"{row['name']} {row['description']} {row['path'] or ''}".strip()

    def _loaded_documents_text(self) -> str:
        return ""

