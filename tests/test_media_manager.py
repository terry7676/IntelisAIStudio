from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from terrygpt.config import load_config
from terrygpt.core.manager import CoreManager
from terrygpt.media.manager import MediaManager
from terrygpt.media.models import ImageGenerationRequest, ImageGenerationResult, ProviderInfo
from terrygpt.media.provider import MediaProvider, ProgressCallback


class FakeImageProvider(MediaProvider):
    @property
    def name(self) -> str:
        return "fake_image"

    def info(self) -> ProviderInfo:
        return ProviderInfo(self.name, True, "Fake provider for tests")

    def generate(
        self,
        request: ImageGenerationRequest,
        output_path: Path,
        progress_callback: ProgressCallback | None = None,
    ) -> ImageGenerationResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if progress_callback is not None:
            progress_callback(50, "Generating fake image", None)
        output_path.write_bytes(b"fake-image")
        if progress_callback is not None:
            progress_callback(100, "Fake image complete", None)
        return ImageGenerationResult(
            id=output_path.stem,
            prompt=request.prompt,
            provider_name=self.name,
            output_path=output_path.resolve(),
            created_at="2026-01-01T00:00:00+00:00",
            seed=request.seed,
            negative_prompt=request.negative_prompt,
        )


def write_config(root: Path) -> Path:
    (root / "config").mkdir()
    (root / "plugins").mkdir()
    path = root / "config" / "default.toml"
    path.write_text(
        """
[database]
path = "data/test.sqlite"
[logging]
path = "data/logs/application.log"
level = "INFO"
[ollama]
base_url = "http://127.0.0.1:11434"
default_model = ""
request_timeout_seconds = 1
[api]
host = "127.0.0.1"
port = 8765
token_path = "data/secrets.toml"
[plugins]
directory = "plugins"
[desktop]
start_api_with_desktop = false
[media]
enabled = true
default_provider = "fake_image"
output_directory = "data/media"
model_id = "runwayml/stable-diffusion-v1-5"
num_inference_steps = 20
guidance_scale = 7.5
negative_prompt = "test-negative"
""",
        encoding="utf-8",
    )
    return path


class MediaManagerTests(unittest.TestCase):
    def test_generate_image_with_fake_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config_path = write_config(Path(temp))
            config = load_config(config_path)
            manager = MediaManager(config)

            class FakeEventBus:
                @staticmethod
                def publish(*_args, **_kwargs):
                    return None

            class FakeContext:
                core = None
                event_bus = FakeEventBus()

            manager.context = FakeContext()  # type: ignore[assignment]
            manager.register_provider(FakeImageProvider())
            manager.settings().output_directory.mkdir(parents=True, exist_ok=True)

            result = manager.generate_image("A red robot in Times Square", provider_name="fake_image")
            self.assertTrue(result.output_path.exists())
            self.assertEqual(result.prompt, "A red robot in Times Square")
            self.assertEqual(result.provider_name, "fake_image")

    def test_media_manager_registers_in_core(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            config_path = write_config(Path(temp))
            core = CoreManager.build(config_path)
            core.initialize()
            core.start()
            try:
                module = core.module("media_manager")
                self.assertIsInstance(module, MediaManager)
                providers = module.list_providers()
                self.assertTrue(any(provider.name == "stable_diffusion" for provider in providers))
            finally:
                core.stop()


if __name__ == "__main__":
    unittest.main()
