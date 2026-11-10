"""Rank whole photos of a single ingredient with local OpenAI CLIP weights."""
import argparse
import csv
from pathlib import Path
import sys
import time

import clip
from clip.model import build_model
from clip.clip import _transform
import torch
from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from food_recognition.catalog import load_catalog


@torch.inference_mode()
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photos", type=Path)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--references", type=Path, help="Optional reference photos in folders named by Chinese catalog label")
    args = parser.parse_args()
    torch.set_num_threads(4)
    with args.weights.open("rb") as stream:
        archive = torch.jit.load(stream, map_location="cpu")
    model = build_model(archive.state_dict()).float().eval()
    del archive
    preprocess = _transform(model.visual.input_resolution)
    foods = load_catalog()["classes"]
    names = [food["name_zh"] for food in foods] + ["无食材"]
    labels = [food["prompt"] for food in foods]
    prompts = [[f"a photo of {label}", f"a close-up of {label}"] for label in labels]
    prompts.append(["an empty kitchen shelf", "an empty plate with no food"])
    tokens = clip.tokenize([p for pair in prompts for p in pair])
    vectors = torch.cat([model.encode_text(batch) for batch in tokens.split(32)])
    vectors = torch.nn.functional.normalize(vectors).reshape(len(names), 2, -1).mean(1)
    vectors = torch.nn.functional.normalize(vectors)
    def encode_photo(path):
        with Image.open(path) as image:
            pixels = preprocess(ImageOps.exif_transpose(image).convert("RGB")).unsqueeze(0)
        return torch.nn.functional.normalize(model.encode_image(pixels))

    references = {}
    if args.references:
        for folder in sorted(args.references.iterdir()):
            if folder.is_dir() and folder.name in names:
                images = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
                if images:
                    references[folder.name] = torch.cat([encode_photo(p) for p in images])
        if len(references) < 2:
            parser.error("Provide reference images for at least two catalog classes")
    with args.output.open("w", encoding="utf-8-sig", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["文件", "首选", "次选", "第三候选", "参考图匹配", "单图耗时秒"])
        for path in sorted(args.photos.iterdir()):
            if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
                continue
            started = time.perf_counter()
            feature = encode_photo(path)
            top = (feature @ vectors.T)[0].topk(3).indices.tolist()
            ranked = [names[i] for i in top]
            matched = ""
            if references:
                scores = sorted(((float((feature @ refs.T).max()), label)
                                 for label, refs in references.items()), reverse=True)
                score, label = scores[0]
                if score >= 0.82 and score - scores[1][0] >= 0.04:
                    matched = label
                    ranked = [label] + [name for name in ranked if name != label]
            writer.writerow([path.name, *ranked[:3], matched, round(time.perf_counter()-started, 3)])


if __name__ == "__main__":
    main()
