"""
TerryGPT Media Manager

The Media Manager is the central controller for all media-related
operations including image, video, and audio generation.

Future providers:
- Stable Diffusion
- FLUX
- ComfyUI
- Forge
- OpenAI Images
- Google Veo
"""

from pathlib import Path


class MediaManager:
    """Central manager for TerryGPT media services."""

    def __init__(self):
        self.providers = {}
        self.jobs = []
        self.output_directory = Path("data/media")
        self.output_directory.mkdir(parents=True, exist_ok=True)

    def register_provider(self, name, provider):
        """Register a media provider."""
        self.providers[name] = provider

    def get_provider(self, name):
        """Return a registered provider."""
        return self.providers.get(name)

    def list_providers(self):
        """Return all provider names."""
        return list(self.providers.keys())