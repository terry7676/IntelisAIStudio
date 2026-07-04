from abc import ABC, abstractmethod


class MediaProvider(ABC):
    """Base class for all TerryGPT media providers."""

    @abstractmethod
    def generate(self, prompt: str):
        """Generate media from a prompt."""
        raise NotImplementedError