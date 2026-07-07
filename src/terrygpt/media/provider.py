from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from terrygpt.media.models import ImageGenerationRequest, ImageGenerationResult, ProviderInfo


ProgressCallback = Callable[[int, str, bytes | None], None]


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
    def generate(
        self,
        request: ImageGenerationRequest,
        output_path: Path,
        progress_callback: ProgressCallback | None = None,
    ) -> ImageGenerationResult:
        raise NotImplementedError
