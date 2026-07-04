"""
ComfyUI Provider

Provides image generation through a local ComfyUI server.
"""

from terrygpt.media.provider import MediaProvider


class ComfyUIProvider(MediaProvider):
    """Media provider for ComfyUI."""

    def __init__(self, base_url: str = "http://127.0.0.1:8188"):
        self.base_url = base_url

    def generate(self, prompt: str):
        raise NotImplementedError("ComfyUI generation not implemented yet.")