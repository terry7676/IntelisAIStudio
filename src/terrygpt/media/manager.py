from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from terrygpt.configuration.manager import ConfigurationManager
from terrygpt.core.module import BaseModule, ModuleHealth
from terrygpt.database.manager import new_id, utc_now
from terrygpt.media.images.diffusers_provider import StableDiffusionProvider
from terrygpt.media.videos.generator import VideoGenerator
from terrygpt.media.models import ImageGenerationRequest, ImageGenerationResult, ProviderInfo
from terrygpt.media.provider import MediaProvider, ProgressCallback

if TYPE_CHECKING:
    from terrygpt.config import TerryConfig


@dataclass(frozen=True)
class MediaSettings:
    enabled: bool = True
    default_provider: str = "stable_diffusion"
    output_directory: Path = Path("data/media")
    model_id: str = "stabilityai/stable-diffusion-2-1"
    num_inference_steps: int = 40
    guidance_scale: float = 8.0
    negative_prompt: str = (
        "blurry, low quality, black image, dark, distorted, "
        "deformed, cropped, watermark, text"
    )


class MediaManager(BaseModule):
    """Central controller for TerryGPT media operations."""

    def __init__(self, config: "TerryConfig") -> None:
        super().__init__(name="media_manager", dependencies=("configuration",))
        self._config = config
        self._providers: dict[str, MediaProvider] = {}
        self._jobs: list[ImageGenerationResult] = []
        self._settings_cache: MediaSettings | None = None
        self.configuration: ConfigurationManager | None = None

    def on_initialize(self) -> None:
        self.configuration = self._module("configuration", ConfigurationManager)
        settings = self.settings()
        settings.output_directory.mkdir(parents=True, exist_ok=True)

        stable_diffusion = StableDiffusionProvider(
            model_id=settings.model_id,
            default_negative_prompt=settings.negative_prompt,
        )
        self._providers[stable_diffusion.name] = stable_diffusion

        video_gen = VideoGenerator()
        self._providers[video_gen.name] = video_gen

        if self.context is not None:
            self.context.event_bus.publish(
                "media.initialized",
                {"providers": [provider.info().__dict__ for provider in self._providers.values()]},
                source=self.name,
            )

    def settings(self) -> MediaSettings:
        if self._settings_cache is not None:
            return self._settings_cache

        runtime = {}
        if self.configuration is not None:
            runtime = self.configuration.get_category("media")

        media_config = self._config.media
        output_value = runtime.get("output_directory", media_config.output_directory)
        if isinstance(output_value, Path):
            output_directory = output_value if output_value.is_absolute() else self._config.project_root / output_value
        else:
            output_directory = self._config.project_root / str(output_value)

        self._settings_cache = MediaSettings(
            enabled=bool(runtime.get("enabled", media_config.enabled)),
            default_provider=str(runtime.get("default_provider", media_config.default_provider)),
            output_directory=output_directory.resolve(),
            model_id=str(runtime.get("model_id", media_config.model_id)),
            num_inference_steps=int(runtime.get("num_inference_steps", media_config.num_inference_steps)),
            guidance_scale=float(runtime.get("guidance_scale", media_config.guidance_scale)),
            negative_prompt=str(runtime.get("negative_prompt", media_config.negative_prompt)),
        )
        return self._settings_cache

    def register_provider(self, provider: MediaProvider) -> None:
        self._providers[provider.name] = provider

    def list_providers(self) -> list[ProviderInfo]:
        return [provider.info() for provider in self._providers.values()]

    def generate_image(
        self,
        prompt: str,
        *,
        negative_prompt: str = "",
        provider_name: str = "",
        seed: int | None = None,
        num_inference_steps: int | None = None,
        guidance_scale: float | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ImageGenerationResult:
        settings = self.settings()
        if not settings.enabled:
            raise RuntimeError("Image generation is disabled in settings.")

        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ValueError("Image prompt cannot be empty.")

        selected_provider = provider_name or settings.default_provider
        provider = self._providers.get(selected_provider)
        if provider is None:
            available = ", ".join(self._providers) or "none"
            raise ValueError(f"Unknown media provider '{selected_provider}'. Available: {available}")

        provider_info = provider.info()
        if not provider_info.available:
            raise RuntimeError(provider_info.detail)

        request = ImageGenerationRequest(
            prompt=clean_prompt,
            negative_prompt=negative_prompt or settings.negative_prompt,
            provider_name=selected_provider,
            seed=seed,
            num_inference_steps=num_inference_steps or settings.num_inference_steps,
            guidance_scale=guidance_scale if guidance_scale is not None else settings.guidance_scale,
        )

        output_path = settings.output_directory / f"{new_id()}.png"
        if self.context is not None:
            self.context.event_bus.publish(
                "media.generation.started",
                {"provider": selected_provider, "prompt": clean_prompt},
                source=self.name,
            )

        def _publish_progress(value: int, message: str, image_data: bytes | None = None) -> None:
            if self.context is not None:
                self.context.event_bus.publish(
                    "media.generation.progress",
                    {"provider": selected_provider, "progress": value, "message": message},
                    source=self.name,
                )
            if progress_callback is not None:
                progress_callback(value, message, image_data)

        try:
            result = provider.generate(request, output_path, progress_callback=_publish_progress)
        except Exception as exc:
            if self.context is not None:
                self.context.event_bus.publish(
                    "media.generation.failed",
                    {"provider": selected_provider, "error": str(exc)},
                    source=self.name,
                )
            raise

        self._jobs.append(result)
        if self.context is not None:
            self.context.event_bus.publish(
                "media.generation.completed",
                {"id": result.id, "path": str(result.output_path)},
                source=self.name,
            )
        return result

    def create_slideshow_video(
        self,
        image_paths: list[Path],
        output_path: Path,
        duration_per_image: float = 2.0,
    ) -> dict[str, object]:
        if not image_paths:
            raise ValueError("At least one image is required to create a slideshow video.")

        provider = self._providers.get("video_generator")
        if provider is None:
            raise RuntimeError("Video provider is unavailable.")

        provider_info = provider.info()
        if not provider_info.available:
            raise RuntimeError(provider_info.detail)

        if self.context is not None:
            self.context.event_bus.publish(
                "media.video.started",
                {"image_count": len(image_paths), "output_path": str(output_path)},
                source=self.name,
            )

        try:
            result = provider.create_slideshow(
                image_paths,
                output_path,
                duration_per_image=duration_per_image,
            )
        except Exception as exc:
            if self.context is not None:
                self.context.event_bus.publish(
                    "media.video.failed",
                    {"error": str(exc)},
                    source=self.name,
                )
            raise

        if self.context is not None:
            self.context.event_bus.publish(
                "media.video.completed",
                {"output_path": str(output_path)},
                source=self.name,
            )
        return result

    def list_recent_images(self, limit: int = 20) -> list[ImageGenerationResult]:
        settings = self.settings()
        if not settings.output_directory.exists():
            return []

        images: list[ImageGenerationResult] = []
        for path in sorted(settings.output_directory.glob("*.png"), key=lambda item: item.stat().st_mtime, reverse=True):
            timestamp = utc_now()
            try:
                timestamp = str(path.stat().st_mtime)
            except OSError:
                pass
            images.append(
                ImageGenerationResult(
                    id=path.stem,
                    prompt=path.stem,
                    provider_name="unknown",
                    output_path=path.resolve(),
                    created_at=timestamp,
                )
            )
            if len(images) >= limit:
                break
        return images

    def health(self) -> ModuleHealth:
        available = [provider.name for provider in self._providers.values() if provider.info().available]
        detail = f"{len(available)} image provider(s) ready"
        if not available:
            detail = "No image providers available. Install torch and diffusers for Stable Diffusion."
        return ModuleHealth(self.name, self.state, True, detail)

    def _module(self, name: str, expected_type):
        if self.context is None or self.context.core is None:
            raise RuntimeError("MediaManager requires CoreManager access.")
        module = self.context.core.module(name)
        if not isinstance(module, expected_type):
            raise RuntimeError(f"Registered {name} module is invalid.")
        return module
