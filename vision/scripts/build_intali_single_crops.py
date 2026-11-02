# -*- coding: utf-8 -*-
"""Build single-object IntAli crops for classifier domain evaluation."""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import yaml
from PIL import Image, ImageOps
from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_produce_v1"))
    parser.add_argument("--classifier", type=Path, required=True)
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_single_crops_v1"))
    args = parser.parse_args()

    import torch
    checkpoint = torch.load(args.classifier, map_location="cpu")
    classifier_classes = set(checkpoint["classes"])
    names = {int(k): v for k, v in yaml.safe_load((args.dataset / "data.yaml").read_text(encoding="utf-8"))["names"].items()}
    if args.output.exists():
        shutil.rmtree(args.output)
    (args.output / "test").mkdir(parents=True, exist_ok=True)

    kept = 0
    for label in sorted((args.dataset / "labels" / "test").glob("*.txt")):
        image_path = next((args.dataset / "images" / "test").glob(label.stem + ".*"), None)
        if image_path is None:
            continue
        rows = []
        for line in label.read_text(encoding="utf-8").splitlines():
            p = line.split()
            if len(p) != 5:
                continue
            name = names[int(p[0])]
            safe = name.split("/")[0].replace(" ", "_")
            if safe in classifier_classes:
                rows.append((safe, p[1:]))
        if len(rows) != 1:
            continue
        safe, (cx, cy, w, h) = rows[0]
        cx, cy, w, h = map(float, (cx, cy, w, h))
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            x1 = max(0, int((cx - w / 2) * width - w * width * 0.1))
            y1 = max(0, int((cy - h / 2) * height - h * height * 0.1))
            x2 = min(width, int((cx + w / 2) * width + w * width * 0.1))
            y2 = min(height, int((cy + h / 2) * height + h * height * 0.1))
            crop = im.crop((x1, y1, x2, y2))
            crop = ImageOps.pad(crop, (256, 256), color=(127, 127, 127), method=Image.Resampling.BILINEAR)
            dst = args.output / "test" / safe / f"{label.stem}.jpg"
            dst.parent.mkdir(parents=True, exist_ok=True)
            crop.save(dst, quality=92)
            kept += 1
    print(json.dumps({"single_object_crops": kept, "classes": len(classifier_classes)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
