from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    negative_prompt: str = ""
    provider_name: str = ""
    seed: int | None = None
    num_inference_steps: int = 40
    guidance_scale: float = 8.0


@dataclass(frozen=True)
class ImageGenerationResult:
    id: str
    prompt: str
    provider_name: str
    output_path: Path
    created_at: str
    seed: int | None = None
    negative_prompt: str = ""


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    available: bool
    detail: str
