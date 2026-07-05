"""
ComfyUI Provider

Provides image generation through a local ComfyUI server.
"""

from __future__ import annotations

from pathlib import Path

from terrygpt.media.models import ImageGenerationRequest, ImageGenerationResult, ProviderInfo
from terrygpt.media.provider import MediaProvider


class ComfyUIProvider(MediaProvider):
    """Media provider for ComfyUI."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        self.base_url = base_url

    @property
    def name(self) -> str:
        return "comfyui"

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.name, False, "ComfyUI generation is not implemented yet.")

    def generate(self, request: ImageGenerationRequest, output_path: Path) -> ImageGenerationResult:
        raise NotImplementedError("ComfyUI generation is not implemented yet.")
