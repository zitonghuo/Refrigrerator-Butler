"""Whole-image recognition for a photo of one ingredient."""
from pathlib import Path

import clip
import torch
from clip.clip import _transform
from clip.model import build_model
from PIL import Image, ImageOps

from .catalog import load_catalog


class SingleFoodRecognizer:
    @torch.inference_mode()
    def __init__(self, weights: Path, references: Path):
        with weights.open("rb") as stream:
            archive = torch.jit.load(stream, map_location="cpu")
        self.model = build_model(archive.state_dict()).float().eval()
        self.transform = _transform(self.model.visual.input_resolution)
        foods = load_catalog()["classes"]
        self.names = [f["name_zh"] for f in foods] + ["无食材"]
        prompts = [[f"a photo of {f['prompt']}", f"a close-up of {f['prompt']}"] for f in foods]
        prompts.append(["an empty kitchen shelf", "an empty plate with no food"])
        tokens = clip.tokenize([text for pair in prompts for text in pair])
        vectors = torch.cat([self.model.encode_text(batch) for batch in tokens.split(32)])
        vectors = torch.nn.functional.normalize(vectors).reshape(len(self.names), 2, -1).mean(1)
        self.text = torch.nn.functional.normalize(vectors)
        self.references = {}
        for folder in sorted(references.iterdir()):
            if folder.is_dir() and folder.name in self.names:
                images = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
                if images:
                    self.references[folder.name] = torch.cat([self.encode(p) for p in images])
        if len(self.references) < 2:
            raise ValueError("At least two labeled reference folders are required")

    def encode(self, path):
        with Image.open(path) as image:
            pixels = self.transform(ImageOps.exif_transpose(image).convert("RGB")).unsqueeze(0)
        return torch.nn.functional.normalize(self.model.encode_image(pixels))

    @torch.inference_mode()
    def predict(self, path):
        feature = self.encode(path)
        logits = (feature @ self.text.T)[0]
        scores, ids = logits.topk(2)
        primary, second = (self.names[i] for i in ids.tolist())
        if primary == "无食材":
            return []
        matches = sorted(((float((feature @ refs.T).max()), name)
                          for name, refs in self.references.items()), reverse=True)
        (similarity, reference), (runner_up, _) = matches[:2]
        alternatives = []
        if similarity >= 0.82 and similarity - runner_up >= 0.04:
            if reference != primary:
                # Keep a decisive text match first. Both choices describe the same item.
                if float(scores[0] - scores[1]) < 0.025:
                    primary, reference = reference, primary
                alternatives.append(reference)
        elif float(scores[0] - scores[1]) < 0.025 and second != "无食材":
            alternatives.append(second)
        return [{"name": primary, "alternatives": alternatives, "quantity": None}]
