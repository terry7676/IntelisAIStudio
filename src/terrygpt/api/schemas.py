from __future__ import annotations

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=120)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    conversation_id: str | None = None
    model: str | None = None


class RenameConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class BrainSettingsRequest(BaseModel):
    default_model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    maximum_tokens: int | None = Field(default=None, ge=1, le=32768)
    streaming_enabled: bool | None = None
    memory_enabled: bool | None = None
    system_prompt: str | None = None


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


class ImageGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1)
    negative_prompt: str | None = None
    provider: str | None = None
    seed: int | None = None
    num_inference_steps: int | None = Field(default=None, ge=1, le=150)
    guidance_scale: float | None = Field(default=None, ge=0, le=30)
