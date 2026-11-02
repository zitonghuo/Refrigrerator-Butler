# -*- coding: utf-8 -*-
"""Download a raw-produce-only COCO subset (apple/banana/orange/broccoli/carrot)."""
from __future__ import annotations

import argparse
import json
import random
import urllib.request
from pathlib import Path

TARGETS = {52: "banana", 53: "apple", 55: "orange", 56: "broccoli", 57: "carrot"}
EXCLUDE_FOOD = {54, 58, 59, 60, 61}  # sandwich, hot dog, pizza, donut, cake


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--coco", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\coco_raw"))
    parser.add_argument("--lvis", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\fruits_vegetables_lvis_full"))
    parser.add_argument("--limit", type=int, default=1500)
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\coco_produce_v1"))
    args = parser.parse_args()

    data = json.loads((args.coco / "annotations" / "instances_train2017.json").read_text(encoding="utf-8"))
    images = {img["id"]: img for img in data["images"]}
    target_anns = []
    excluded = set()
    for ann in data["annotations"]:
        if ann["category_id"] in TARGETS:
            target_anns.append(ann)
        elif ann["category_id"] in EXCLUDE_FOOD:
            excluded.add(ann["image_id"])

    by_image = {}
    for ann in target_anns:
        by_image.setdefault(ann["image_id"], []).append(ann)

    lvis_ids = set()
    for image in (args.lvis / "images").rglob("*.jpg"):
        lvis_ids.add(image.stem)
    for image in (args.lvis / "images").rglob("*.png"):
        lvis_ids.add(image.stem)

    candidates = []
    for image_id, anns in by_image.items():
        if image_id in excluded:
            continue
        image = images.get(image_id)
        if image is None:
            continue
        if Path(image["file_name"]).stem in lvis_ids:
            continue
        candidates.append((image_id, image, anns))
    candidates.sort(key=lambda x: x[0])
    random.Random(42).shuffle(candidates)
    candidates = candidates[: args.limit]

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "images").mkdir(exist_ok=True)
    (args.output / "labels").mkdir(exist_ok=True)
    saved = []
    for index, (image_id, image, anns) in enumerate(candidates, start=1):
        name = image["file_name"]
        dst_image = args.output / "images" / name
        if not dst_image.exists():
            url = f"http://images.cocodataset.org/train2017/{name}"
            try:
                urllib.request.urlretrieve(url, dst_image)
            except Exception as exc:
                print("skip", name, exc)
                continue
        width, height = image["width"], image["height"]
        rows = []
        for ann in anns:
            x, y, w, h = ann["bbox"]
            if w < 8 or h < 8:
                continue
            cx = (x + w / 2) / width
            cy = (y + h / 2) / height
            rows.append(f"{sorted(TARGETS).index(ann['category_id'])} {cx:.6f} {cy:.6f} {w / width:.6f} {h / height:.6f}")
        if not rows:
            continue
        (args.output / "labels" / (Path(name).stem + ".txt")).write_text("\n".join(rows) + "\n", encoding="utf-8")
        saved.append({"image": name, "boxes": len(rows)})
        if index % 100 == 0:
            print(index, "downloaded")
    (args.output / "manifest.json").write_text(json.dumps({"targets": TARGETS, "images": saved}, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", len(saved), "images")


if __name__ == "__main__":
    main()
