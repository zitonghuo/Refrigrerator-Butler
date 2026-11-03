# -*- coding: utf-8 -*-
"""Build an IntAli produce segmentation dataset in YOLO-seg format."""
from __future__ import annotations

import argparse
import json
import os
import random
import shutil
from collections import Counter
from pathlib import Path

import yaml
from ultralytics import YOLO

MAP = {
    "apple": "apple", "avocado": "avocado", "banana": "banana",
    "blueberries": "blueberry", "kiwi": "kiwi fruit", "lemon": "lemon",
    "orange": "orange/orange fruit", "pear": "pear", "pineapple": "pineapple",
    "strawberry": "strawberry", "broccoli": "broccoli",
    "cantaloupe": "cantaloup/cantaloupe", "carrot": "carrot",
    "celery": "celery", "cherry tomatoes": "tomato",
    "cucumber": "cucumber/cuke", "garlic": "garlic/ail",
    "green onion": "green onion/spring onion/scallion",
    "green peas": "pea/pea food", "green pepper": "bell pepper/capsicum",
    "hot pepper": "chili/chili vegetable/chili pepper/chili pepper vegetable/chilli/chilli vegetable/chilly/chilly",
    "mushroom": "mushroom", "onion": "onion", "potato": "potato",
    "radish": "radish/daikon", "tomato": "tomato",
}


def polygon_area(points):
    if points and isinstance(points[0], (int, float)):
        points = [(points[i], points[i + 1]) for i in range(0, len(points) - 1, 2)]
    area = 0.0
    for i in range(len(points)):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"C:\Users\ALIENWARE\.cache\kagglehub\datasets\miketrs\intali-food-dataset\versions\1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_produce_seg_v1"))
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
    for split in ("train", "test"):
        data = json.loads((args.source / f"{split}.json").read_text(encoding="utf-8"))
        cats = {c["id"]: c["name"].strip().lower() for c in data["categories"]}
        anns = {}
        for ann in data["annotations"]:
            name = cats[ann["category_id"]]
            if name not in mapping:
                continue
            seg = ann.get("segmentation") or []
            if isinstance(seg, dict):
                seg = seg.get("counts", [])
            polygons = [p for p in seg if isinstance(p, list) and len(p) >= 6]
            if not polygons:
                x, y, w, h = ann["bbox"]
                polygons = [[x, y, x + w, y, x + w, y + h, x, y + h]]
            polygon = max(polygons, key=polygon_area)
            points = [(polygon[i], polygon[i + 1]) for i in range(0, len(polygon) - 1, 2)]
            if len(points) < 3:
                continue
            anns.setdefault(ann["image_id"], []).append((mapping[name], points, data["images"]))
        kept_images = kept_instances = 0
        for image in data["images"]:
            rows = []
            for cid, points, _ in anns.get(image["id"], []):
                coords = []
                for x, y in points:
                    coords.append(f"{min(1, max(0, x / image['width'])):.6f}")
                    coords.append(f"{min(1, max(0, y / image['height'])):.6f}")
                if len(coords) >= 6:
                    rows.append(f"{cid} {' '.join(coords)}")
            if not rows:
                continue
            src = args.source / "images" / image["file_name"]
            if not src.exists():
                continue
            split_out = split
            # split official train 90/10 into train/val
            dst_stem = image["file_name"].replace("/", "__")
            if split == "train" and random.Random(hash(dst_stem) & 0xFFFF).random() < 0.1:
                split_out = "val"
            dst = args.output / "images" / split_out / dst_stem
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            (args.output / "labels" / split_out / (dst.stem + ".txt")).write_text("\n".join(rows) + "\n", encoding="utf-8")
            kept_images += 1
            kept_instances += len(rows)
        totals[split] = {"images": kept_images, "instances": kept_instances}

    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    for i, name in target.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({"splits": totals, "classes": len(mapping)}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"classes": len(mapping), "splits": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
