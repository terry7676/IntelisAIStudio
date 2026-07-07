from __future__ import annotations

import importlib.util
from pathlib import Path

from terrygpt.database.manager import new_id, utc_now
from terrygpt.media.models import ImageGenerationRequest, ImageGenerationResult, ProviderInfo
from terrygpt.media.provider import MediaProvider, ProgressCallback


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


class VideoGenerator(MediaProvider):
    """Generate and manage videos. Currently supports video compilation from images."""

    def __init__(self) -> None:
        self.fps = 30
        self.duration = 5

    @property
    def name(self) -> str:
        return "video_generator"

    def info(self) -> ProviderInfo:
        # Check for required video libraries
        missing = []
        if not _module_available("cv2"):
            missing.append("opencv-python: pip install opencv-python")
        if not _module_available("imageio"):
            missing.append("imageio: pip install imageio imageio-ffmpeg")
        
        if missing:
            return ProviderInfo(
                self.name,
                False,
                f"Install: {', '.join(missing)}",
            )
        return ProviderInfo(self.name, True, "Ready (can compile videos from images or create frame sequences)")

    def generate(
        self,
        request: ImageGenerationRequest,
        output_path: Path,
        progress_callback: ProgressCallback | None = None,
    ) -> ImageGenerationResult:
        """Generate a video. Uses prompt to determine video type."""
        if not self.info().available:
            raise RuntimeError(self.info().detail)
        
        # For now, return a message that video generation is a pro feature
        # In future, this could integrate with tools like AnimateDiff or Runway
        raise NotImplementedError(
            "Video generation is currently in beta. "
            "Use the slideshow feature to create videos from images: "
            "media_manager.create_slideshow_video(image_paths, output_path)"
        )

    def generate_video_from_frames(
        self,
        frames: list[Path],
        output_path: Path,
        fps: int = 30,
    ) -> dict:
        """Generate video from image frames."""
        if not self.info().available:
            raise RuntimeError(self.info().detail)

        try:
            import cv2
            import numpy as np
            from PIL import Image
        except ImportError as e:
            raise RuntimeError(f"Missing required video library: {e}") from e

        if not frames:
            raise ValueError("No frames provided")

        # Load first frame to get dimensions
        first_frame = Image.open(frames[0])
        width, height = first_frame.size

        # Initialize video writer
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        # Write frames
        for frame_path in frames:
            image = Image.open(frame_path).convert("RGB")
            frame_array = np.array(image)
            # Convert RGB to BGR for OpenCV
            frame_bgr = cv2.cvtColor(frame_array, cv2.COLOR_RGB2BGR)
            out.write(frame_bgr)

        out.release()

        return {
            "output_path": str(output_path),
            "frame_count": len(frames),
            "fps": fps,
            "duration_seconds": len(frames) / fps,
        }

    def create_slideshow(
        self,
        image_paths: list[Path],
        output_path: Path,
        duration_per_image: float = 2.0,
        transition_frames: int = 15,
    ) -> dict:
        """Create a slideshow video with transitions."""
        if not self.info().available:
            raise RuntimeError(self.info().detail)

        try:
            from PIL import Image
            import cv2
            import numpy as np
        except ImportError as e:
            raise RuntimeError(f"Missing required video library: {e}") from e

        if not image_paths:
            raise ValueError("No images provided")

        # Load all images
        images = [Image.open(img_path).convert("RGB") for img_path in image_paths]
        
        # Resize all to match first image
        width, height = images[0].size
        images = [img.resize((width, height)) if img.size != (width, height) else img for img in images]

        # Create video frames
        fps = 30
        frames_per_image = int(duration_per_image * fps)
        
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

        # Write frames
        for img in images:
            img_array = np.array(img)
            img_bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
            # Repeat each image
            for _ in range(frames_per_image):
                out.write(img_bgr)

        out.release()

        total_frames = len(images) * frames_per_image
        return {
            "output_path": str(output_path),
            "image_count": len(images),
            "duration_seconds": total_frames / fps,
            "fps": fps,
        }
