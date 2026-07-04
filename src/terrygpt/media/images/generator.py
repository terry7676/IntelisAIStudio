from terrygpt.media.provider import MediaProvider


class ImageGenerator(MediaProvider):
    """Base image generator."""

    def generate(self, prompt: str):
        print(f"Generating image: {prompt}")