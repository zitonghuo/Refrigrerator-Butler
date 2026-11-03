# -*- coding: utf-8 -*-
"""Build a cleaner IntAli segmentation set: drop prepared/processed dish labels."""
from __future__ import annotations

import argparse
import json
import random
import shutil
from pathlib import Path

import yaml
from ultralytics import YOLO

from build_intali_produce import MAP

BAD_SUPER = {
    "Half-cooked meals", "Cereal based products", "Canned Foods",
    "Sweets", "Spices, Flavourings, Sauces & cooking/baking aids",
    "Drinks", "Others",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"C:\Users\ALIENWARE\.cache\kagglehub\datasets\miketrs\intali-food-dataset\versions\1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_clean_seg_v1"))
    args = parser.parse_args()

    target = {int(k): v for k, v in YOLO(str(args.weights)).names.items()}
    target_by_name = {v: i for i, v in target.items()}
    mapping = {k: target_by_name[v] for k, v in MAP.items() if v in target_by_name}
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    totals = {}
    for source_split in ("train", "test"):
        data = json.loads((args.source / f"{source_split}.json").read_text(encoding="utf-8"))
        cats = {c["id"]: c for c in data["categories"]}
        anns = {}
        for ann in data["annotations"]:
            anns.setdefault(ann["image_id"], []).append(ann)
        kept_images = kept_instances = 0
        for image in data["images"]:
            image_anns = anns.get(image["id"], [])
            if not image_anns:
                continue
            if any(cats[a["category_id"]]["supercategory"] in BAD_SUPER for a in image_anns):
                continue
            if not any(cats[a["category_id"]]["supercategory"] in ("Fruits", "Vegetables") for a in image_anns):
                continue
            rows = []
            for ann in image_anns:
                name = cats[ann["category_id"]]["name"].strip().lower()
                if name not in mapping:
                    continue
                seg = ann.get("segmentation") or []
                polygons = [p for p in seg if isinstance(p, list) and len(p) >= 6]
                if not polygons:
                    x, y, w, h = ann["bbox"]
                    polygons = [[x, y, x + w, y, x + w, y + h, x, y + h]]
                polygon = max(polygons, key=lambda p: len(p))
                coords = []
                for i in range(0, len(polygon) - 1, 2):
                    coords.append(f"{min(1, max(0, polygon[i] / image['width'])):.6f}")
                    coords.append(f"{min(1, max(0, polygon[i + 1] / image['height'])):.6f}")
                if len(coords) >= 6:
                    rows.append(f"{mapping[name]} {' '.join(coords)}")
            if not rows:
                continue
            src = args.source / "images" / image["file_name"]
            if not src.exists():
                continue
            split = source_split
            dst_stem = image["file_name"].replace("/", "__")
            if source_split == "train" and random.Random(int(image["id"]) + 42).random() < 0.1:
                split = "val"
            dst = args.output / "images" / split / dst_stem
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            (args.output / "labels" / split / (dst.stem + ".txt")).write_text("\n".join(rows) + "\n", encoding="utf-8")
            kept_images += 1
            kept_instances += len(rows)
        totals[source_split] = {"images": kept_images, "instances": kept_instances}

    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    for i, name in target.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({"splits": totals, "classes": len(mapping)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"splits": totals, "classes": len(mapping)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
