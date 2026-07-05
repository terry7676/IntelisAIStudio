from pathlib import Path

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Help static type checkers / editors resolve the 'torch' import
    # Some editors report "Import 'torch' could not be resolved" for optional deps;
    # silence that by telling type checkers to ignore unresolved import at edit time.
    import torch  # type: ignore

try:
    import torch  # type: ignore
except Exception:
    print("Error: the 'torch' package is not installed or could not be imported.\n"
          "Install it with: pip install torch --index-url https://download.pytorch.org/whl/cu118")
    sys.exit(1)
try:
    from diffusers import StableDiffusionPipeline  # type: ignore[import]
except Exception:
    print("Error: the 'diffusers' package is not installed or could not be imported.\n"
          "Install it with: pip install diffusers[torch] --extra-index-url https://download.pytorch.org/whl/cu118")
    sys.exit(1)

MODEL_ID = "runwayml/stable-diffusion-v1-5"

print("Loading Stable Diffusion model...")

pipe = StableDiffusionPipeline.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    safety_checker=None,
)

device = "cuda" if torch.cuda.is_available() else "cpu"
pipe = pipe.to(device)

print(f"Running on: {device}")

prompt = (
    "A futuristic robot walking through Times Square at sunset, "
    "cinematic lighting, ultra detailed, masterpiece, 8k, "
    "high quality, sharp focus, realistic"
)

generator = torch.Generator(device=device).manual_seed(42)

image = pipe(
    prompt=prompt,
    negative_prompt=(
        "blurry, low quality, black image, dark, distorted, "
        "deformed, cropped, watermark, text"
    ),
    num_inference_steps=40,
    guidance_scale=8.0,
    generator=generator,
).images[0]

output_dir = Path("data/media")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "first_image.png"
image.save(output_file)

print()
print("=" * 50)
print("SUCCESS!")
print(f"Image saved to: {output_file.resolve()}")
print("=" * 50)