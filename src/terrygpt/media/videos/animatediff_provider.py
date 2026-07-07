from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

from terrygpt.database.manager import new_id, utc_now
from terrygpt.media.models import ProviderInfo
from terrygpt.media.provider import MediaProvider, ProgressCallback

if TYPE_CHECKING:
    pass


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


class AnimateDiffProvider(MediaProvider):
    """Generate realistic videos with text-to-video using AnimateDiff + Stable Diffusion."""

    def __init__(
        self,
        base_model: str = "stabilityai/stable-diffusion-xl-base-1.0",
        motion_model: str = "guoyww/animatediff-motion-adapter-v1-5-2",
        num_frames: int = 16,
        height: int = 512,
        width: int = 512,
    ) -> None:
        self.base_model = base_model
        self.motion_model = motion_model
        self.num_frames = num_frames
        self.height = height
        self.width = width
        self._pipeline = None
        self._device = "cpu"

    @property
    def name(self) -> str:
        return "animatediff"

    def info(self) -> ProviderInfo:
        missing = []
        if not _module_available("torch"):
            missing.append("torch")
        if not _module_available("diffusers"):
            missing.append("diffusers")
        if not _module_available("transformers"):
            missing.append("transformers")

        if missing:
            deps = ", ".join(missing)
            return ProviderInfo(
                self.name,
                False,
                f"Install: pip install {deps} imageio imageio-ffmpeg",
            )

        return ProviderInfo(
            self.name,
            True,
            f"Ready (text-to-video with {self.num_frames} frames, {self.width}x{self.height})",
        )

    def generate(
        self,
        prompt: str,
        output_path: Path,
        negative_prompt: str = "",
        num_frames: int | None = None,
        guidance_scale: float = 7.5,
        progress_callback: ProgressCallback | None = None,
    ) -> dict:
        """Generate a video from a text prompt using AnimateDiff."""
        if not self.info().available:
            raise RuntimeError(self.info().detail)

        import torch
        from diffusers import AnimateDiffPipeline, DDIMScheduler, MotionAdapter
        from diffusers.utils import export_to_gif

        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ValueError("Video prompt cannot be empty.")

        num_frames = num_frames or self.num_frames

        # Initialize pipeline on first use
        if self._pipeline is None:
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            self._device = "cuda" if torch.cuda.is_available() else "cpu"

            # Load motion adapter
            motion_adapter = MotionAdapter.from_pretrained(self.motion_model, torch_dtype=dtype)

            # Initialize AnimateDiff pipeline
            self._pipeline = AnimateDiffPipeline.from_pretrained(
                self.base_model,
                motion_adapter=motion_adapter,
                torch_dtype=dtype,
            )
            self._pipeline.scheduler = DDIMScheduler(
                num_train_timesteps=1000,
                beta_start=0.00085,
                beta_end=0.012,
                beta_schedule="linear",
                steps_offset=1,
                clip_sample=False,
                set_alpha_to_one=False,
                timestep_spacing="linspace",
            )
            self._pipeline = self._pipeline.to(self._device)

        if progress_callback:
            progress_callback(10, "Initializing animation pipeline...")

        # Generate frames
        if progress_callback:
            progress_callback(20, f"Generating {num_frames} frames...")

        generator = None
        with torch.no_grad():
            frames = self._pipeline(
                prompt=clean_prompt,
                negative_prompt=negative_prompt or (
                    "blurry, low quality, distorted, cartoon, anime, illustration, "
                    "deformed face, bad anatomy, watermark, text"
                ),
                num_frames=num_frames,
                height=self.height,
                width=self.width,
                num_inference_steps=24,
                guidance_scale=guidance_scale,
                generator=generator,
            ).frames[0]

        if progress_callback:
            progress_callback(80, "Encoding video...")

        # Export to video file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save as MP4 using imageio
        try:
            import imageio
        except ImportError:
            raise RuntimeError("Install imageio: pip install imageio imageio-ffmpeg")

        # Convert PIL images to numpy arrays and save
        import numpy as np

        video_frames = [np.array(frame) for frame in frames]
        imageio.mimsave(str(output_path), video_frames, fps=8, codec="libx264")

        if progress_callback:
            progress_callback(100, "Video generated successfully!")

        return {
            "id": new_id(),
            "output_path": str(output_path),
            "prompt": clean_prompt,
            "negative_prompt": negative_prompt,
            "num_frames": num_frames,
            "fps": 8,
            "duration_seconds": num_frames / 8,
            "width": self.width,
            "height": self.height,
            "created_at": utc_now(),
        }

    def create_slideshow(
        self,
        image_paths: list[Path],
        output_path: Path,
        duration_per_image: float = 2.0,
    ) -> dict:
        """Not used for AnimateDiff. Use generate() instead."""
        raise NotImplementedError("Use generate() for text-to-video. This provider does not support image slideshows.")
