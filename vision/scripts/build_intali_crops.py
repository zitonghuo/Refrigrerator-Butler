# -*- coding: utf-8 -*-
"""Build IntAli train/val/test crops for single-item classifier fine-tuning."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import yaml
from PIL import Image, ImageOps
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_produce_v1"))
    parser.add_argument("--classifier", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_crops_v1"))
    args = parser.parse_args()

    import torch
    ckpt = torch.load(args.classifier, map_location="cpu")
    classes = set(ckpt["classes"])
    names = {int(k): v for k, v in yaml.safe_load((args.dataset / "data.yaml").read_text(encoding="utf-8"))["names"].items()}
    if args.output.exists():
        shutil.rmtree(args.output)
    counts = {}
    for split in ("train", "val", "test"):
        (args.output / split).mkdir(parents=True, exist_ok=True)
        n = 0
        for label in sorted((args.dataset / "labels" / split).glob("*.txt")):
            image_path = next((args.dataset / "images" / split).glob(label.stem + ".*"), None)
            if image_path is None:
                continue
            rows = []
            for line in label.read_text(encoding="utf-8").splitlines():
                p = line.split()
                if len(p) != 5:
                    continue
                safe = names[int(p[0])].split("/")[0].replace(" ", "_")
                if safe in classes:
                    rows.append((safe, p[1:]))
            if not rows:
                continue
            with Image.open(image_path) as im:
                im = im.convert("RGB")
                width, height = im.size
                for j, (safe, box) in enumerate(rows):
                    cx, cy, w, h = map(float, box)
                    x1 = max(0, int((cx - w / 2) * width - w * width * 0.1))
                    y1 = max(0, int((cy - h / 2) * height - h * height * 0.1))
                    x2 = min(width, int((cx + w / 2) * width + w * width * 0.1))
                    y2 = min(height, int((cy + h / 2) * height + h * height * 0.1))
                    crop = ImageOps.pad(im.crop((x1, y1, x2, y2)), (256, 256), color=(127, 127, 127), method=Image.Resampling.BILINEAR)
                    dst = args.output / split / safe / f"{label.stem}_{j}.jpg"
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    crop.save(dst, quality=92)
                    n += 1
        counts[split] = n
    print(json.dumps({"crops": counts, "classes": len(classes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
