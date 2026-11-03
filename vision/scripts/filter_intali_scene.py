# -*- coding: utf-8 -*-
"""Automatic scene filter: table/fridge raw ingredients vs cooked/market/package."""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

import clip
import torch
import yaml
from PIL import Image

GROUPS = {
    "table": [
        "raw ingredients on a table",
        "raw vegetables on a cutting board",
        "food ingredients on a kitchen counter",
        "raw meat on a table",
        "groceries on a table",
        "a close-up of raw ingredients",
    ],
    "fridge": [
        "food inside a refrigerator",
        "food on a refrigerator shelf",
        "ingredients in a fridge",
    ],
    "plate": [
        "cooked meal on a plate",
        "a plated dish",
        "cooked food on a plate",
        "a bowl of cooked food",
    ],
    "market": [
        "food at a market stall",
        "vegetables on a supermarket shelf",
    ],
    "package": [
        "packaged food on a table",
        "food in a plastic bag",
    ],
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_produce_v1"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_scene_v2"))
    parser.add_argument("--device", default="0")
    parser.add_argument("--threshold", type=float, default=0.35)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() and args.device != "cpu" else "cpu")
    model, preprocess = clip.load("ViT-B/32", device=device)
    prompts, owners = [], []
    for group, items in GROUPS.items():
        prompts.extend(items)
        owners.extend([group] * len(items))
    tokens = clip.tokenize(prompts).to(device)
    with torch.no_grad():
        text = model.encode_text(tokens)
        text = text / text.norm(dim=-1, keepdim=True)

    if args.output.exists():
        shutil.rmtree(args.output)
    names = {int(k): v for k, v in yaml.safe_load((args.source / "data.yaml").read_text(encoding="utf-8"))["names"].items()}
    report = {}
    kept_counts = Counter()
    total_counts = Counter()
    for split in ("train", "val", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)
        for image_path in sorted((args.source / "images" / split).glob("*.*")):
            label_path = args.source / "labels" / split / (image_path.stem + ".txt")
            if not label_path.exists() or not label_path.read_text(encoding="utf-8").strip():
                continue
            with Image.open(image_path) as im:
                tensor = preprocess(im.convert("RGB")).unsqueeze(0).to(device)
            with torch.no_grad():
                image = model.encode_image(tensor)
                image = image / image.norm(dim=-1, keepdim=True)
                sims = (image @ text.T)[0]
            group_score = {g: float(sims[[i for i, o in enumerate(owners) if o == g]].max()) for g in GROUPS}
            top_group = max(group_score, key=group_score.get)
            probs = torch.softmax(torch.tensor(list(group_score.values())) * 20, dim=0)
            top_prob = float(probs[list(group_score).index(top_group)])
            total_counts[split] += 1
            report[f"{split}/{image_path.name}"] = {"group": top_group, "prob": round(top_prob, 3),
                                                      "scores": {k: round(v, 3) for k, v in group_score.items()}}
            if top_group in ("table", "fridge") and top_prob >= args.threshold:
                shutil.copy2(image_path, args.output / "images" / split / image_path.name)
                (args.output / "labels" / split / label_path.name).write_text(label_path.read_text(encoding="utf-8"), encoding="utf-8")
                kept_counts[split] += 1
    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    for i, name in names.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "filter_report.json").write_text(json.dumps({
        "total": dict(total_counts), "kept": dict(kept_counts),
        "groups": Counter(v["group"] for v in report.values()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    (args.output / "per_image.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"total": dict(total_counts), "kept": dict(kept_counts),
                      "groups": Counter(v["group"] for v in report.values())}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
