"""
TerryGPT Task Router

Determines what type of AI task the user is requesting.
"""

from enum import Enum


class TaskType(Enum):
    CHAT = "chat"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VISION = "vision"
    DOCUMENT = "document"


class TaskRouter:

    IMAGE_KEYWORDS = (
        "draw",
        "create image",
        "generate image",
        "make a picture",
        "paint",
        "illustrate",
        "photo of",
    )

    VIDEO_KEYWORDS = (
        "generate video",
        "create video",
        "make video",
        "animate",
    )

    AUDIO_KEYWORDS = (
        "generate speech",
        "text to speech",
        "voice",
        "read aloud",
    )

    DOCUMENT_KEYWORDS = (
        "summarize pdf",
        "summarize document",
        "analyze pdf",
        "read this document",
    )

    def detect(self, prompt: str) -> TaskType:

        text = prompt.lower()

        if any(word in text for word in self.IMAGE_KEYWORDS):
            return TaskType.IMAGE

        if any(word in text for word in self.VIDEO_KEYWORDS):
            return TaskType.VIDEO

        if any(word in text for word in self.AUDIO_KEYWORDS):
            return TaskType.AUDIO

        if any(word in text for word in self.DOCUMENT_KEYWORDS):
            return TaskType.DOCUMENT

        return TaskType.CHAT