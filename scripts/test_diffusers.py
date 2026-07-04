from pathlib import Path

import torch
from diffusers import StableDiffusionPipeline

MODEL_PATH = r"C:\AI\ComfyUI\models\checkpoints\v1-5-pruned-emaonly-fp16.safetensors"

print("Loading model...")

pipe = StableDiffusionPipeline.from_single_file(
    MODEL_PATH,
    torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    safety_checker=None,
)

device = "cuda" if torch.cuda.is_available() else "cpu"
pipe = pipe.to(device)

print(f"Running on: {device}")

image = pipe(
    "A futuristic robot walking through Times Square at sunset",
    num_inference_steps=20,
).images[0]

output_dir = Path("data/media")
output_dir.mkdir(parents=True, exist_ok=True)

output_file = output_dir / "first_image.png"
image.save(output_file)

print(f"Image saved to {output_file}")