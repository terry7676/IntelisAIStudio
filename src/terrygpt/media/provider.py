from __future__ import annotations

from abc import ABC, abstractmethod

from terrygpt.media.models import ImageGenerationRequest, ImageGenerationResult, ProviderInfo


class MediaProvider(ABC):
    """Base class for all TerryGPT media providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def info(self) -> ProviderInfo:
        raise NotImplementedError

    @abstractmethod
    def generate(self, request: ImageGenerationRequest, output_path) -> ImageGenerationResult:
        raise NotImplementedError
