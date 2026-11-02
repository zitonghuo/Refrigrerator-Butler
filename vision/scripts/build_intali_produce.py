# -*- coding: utf-8 -*-
"""Convert IntAli ingredient images to a 47-class raw-produce YOLO dataset."""
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
    "apple": "apple",
    "avocado": "avocado",
    "banana": "banana",
    "blueberries": "blueberry",
    "kiwi": "kiwi fruit",
    "lemon": "lemon",
    "orange": "orange/orange fruit",
    "pear": "pear",
    "pineapple": "pineapple",
    "strawberry": "strawberry",
    "broccoli": "broccoli",
    "cantaloupe": "cantaloup/cantaloupe",
    "carrot": "carrot",
    "celery": "celery",
    "cherry tomatoes": "tomato",
    "cucumber": "cucumber/cuke",
    "garlic": "garlic/ail",
    "green onion": "green onion/spring onion/scallion",
    "green peas": "pea/pea food",
    "green pepper": "bell pepper/capsicum",
    "hot pepper": "chili/chili vegetable/chili pepper/chili pepper vegetable/chilli/chilli vegetable/chilly/chilly",
    "mushroom": "mushroom",
    "onion": "onion",
    "potato": "potato",
    "radish": "radish/daikon",
    "tomato": "tomato",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"C:\Users\ALIENWARE\.cache\kagglehub\datasets\miketrs\intali-food-dataset\versions\1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_produce_v1"))
    args = parser.parse_args()

    target = {int(k): v for k, v in YOLO(str(args.weights)).names.items()}
    target_by_name = {v: i for i, v in target.items()}
    mapping = {k: target_by_name[v] for k, v in MAP.items() if v in target_by_name}
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = Counter()
    totals = {}
    for split in ("train", "test"):
        data = json.loads((args.source / f"{split}.json").read_text(encoding="utf-8"))
        cats = {c["id"]: c["name"].strip().lower() for c in data["categories"]}
        anns = {}
        for ann in data["annotations"]:
            name = cats[ann["category_id"]]
            if name not in mapping:
                continue
            anns.setdefault(ann["image_id"], []).append((mapping[name], ann["bbox"]))
        kept_images = 0
        kept_boxes = 0
        for image in data["images"]:
            rows = []
            for cid, (x, y, w, h) in anns.get(image["id"], []):
                if w < 8 or h < 8:
                    continue
                cx = (x + w / 2) / image["width"]
                cy = (y + h / 2) / image["height"]
                rows.append(f"{cid} {cx:.6f} {cy:.6f} {w / image['width']:.6f} {h / image['height']:.6f}")
            if not rows:
                continue
            src = args.source / "images" / image["file_name"]
            if not src.exists():
                continue
            dst = args.output / "images" / split / image["file_name"].replace("/", "__")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            (args.output / "labels" / split / (dst.stem + ".txt")).write_text("\n".join(rows) + "\n", encoding="utf-8")
            kept_images += 1
            kept_boxes += len(rows)
            for row in rows:
                stats[int(row.split()[0])] += 1
        totals[split] = {"images": kept_images, "boxes": kept_boxes}

    val_images = args.output / "images" / "val"
    val_labels = args.output / "labels" / "val"
    val_images.mkdir(parents=True, exist_ok=True)
    val_labels.mkdir(parents=True, exist_ok=True)
    train_files = sorted((args.output / "images" / "train").glob("*.*"))
    random.Random(42).shuffle(train_files)
    for image in train_files[: max(1, len(train_files) // 10)]:
        os.replace(image, val_images / image.name)
        label = args.output / "labels" / "train" / (image.stem + ".txt")
        if label.exists():
            os.replace(label, val_labels / label.name)
    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    for i, name in target.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({
        "mapping": MAP, "splits": totals,
        "per_class": {target[i]: stats[i] for i in target},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"classes": len(mapping), "splits": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
