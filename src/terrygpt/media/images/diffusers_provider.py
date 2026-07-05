from __future__ import annotations

import importlib.util
from pathlib import Path

from terrygpt.database.manager import new_id, utc_now
from terrygpt.media.models import ImageGenerationRequest, ImageGenerationResult, ProviderInfo
from terrygpt.media.provider import MediaProvider


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


class StableDiffusionProvider(MediaProvider):
    """Generate images with Hugging Face diffusers and Stable Diffusion."""

    def __init__(
        self,
        model_id: str = "runwayml/stable-diffusion-v1-5",
        default_negative_prompt: str = "",
    ) -> None:
        self.model_id = model_id
        self.default_negative_prompt = default_negative_prompt
        self._pipeline = None
        self._device = "cpu"

    @property
    def name(self) -> str:
        return "stable_diffusion"

    def info(self) -> ProviderInfo:
        if not _module_available("torch"):
            return ProviderInfo(
                self.name,
                False,
                "Install torch: pip install torch --index-url https://download.pytorch.org/whl/cu118",
            )
        if not _module_available("diffusers"):
            return ProviderInfo(
                self.name,
                False,
                "Install diffusers: pip install diffusers[torch]",
            )
        return ProviderInfo(self.name, True, f"Ready ({self.model_id})")

    def generate(self, request: ImageGenerationRequest, output_path: Path) -> ImageGenerationResult:
        if not self.info().available:
            raise RuntimeError(self.info().detail)

        import torch
        from diffusers import StableDiffusionPipeline

        if self._pipeline is None:
            dtype = torch.float16 if torch.cuda.is_available() else torch.float32
            self._pipeline = StableDiffusionPipeline.from_pretrained(
                self.model_id,
                torch_dtype=dtype,
                safety_checker=None,
            )
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
            self._pipeline = self._pipeline.to(self._device)

        negative_prompt = request.negative_prompt or self.default_negative_prompt
        generator = None
        if request.seed is not None:
            generator = torch.Generator(device=self._device).manual_seed(request.seed)

        image = self._pipeline(
            prompt=request.prompt,
            negative_prompt=negative_prompt,
            num_inference_steps=request.num_inference_steps,
            guidance_scale=request.guidance_scale,
            generator=generator,
        ).images[0]

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path)

        return ImageGenerationResult(
            id=new_id(),
            prompt=request.prompt,
            provider_name=self.name,
            output_path=output_path,
            created_at=utc_now(),
            seed=request.seed,
            negative_prompt=negative_prompt,
        )
