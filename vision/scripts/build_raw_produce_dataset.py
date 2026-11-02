# -*- coding: utf-8 -*-
"""Merge LVIS raw produce with the COCO produce subset (47-class model)."""
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

ALIASES = {
    "bell_pepper": "bell pepper/capsicum",
    "corn": "edible corn/corn/maize",
    "green_bean": "green bean",
    "scallion": "green onion/spring onion/scallion",
    "kiwi": "kiwi fruit",
    "mandarin": "mandarin orange",
    "orange": "orange/orange fruit",
    "pea": "pea/pea food",
    "sweet_potato": "sweet potato",
    "zucchini": "zucchini/courgette",
    "cucumber": "cucumber/cuke",
    "eggplant": "eggplant/aubergine",
    "radish": "radish/daikon",
    "cantaloupe": "cantaloup/cantaloupe",
    "chili": "chili/chili vegetable/chili pepper/chili pepper vegetable/chilli/chilli vegetable/chilly/chilly",
    "garlic": "garlic/ail",
    "ginger": "ginger/gingerroot",
    "date": "date/date fruit",
}
COCO = ["banana", "apple", "orange", "broccoli", "carrot"]
COCO_TO = {"banana": "banana", "apple": "apple", "orange": "orange/orange fruit", "broccoli": "broccoli", "carrot": "carrot"}


def parse_names(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data["names"].items()}


def link(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lvis", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\fruits_vegetables_lvis_full"))
    parser.add_argument("--coco", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\coco_produce_v1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\raw_produce_v2"))
    args = parser.parse_args()

    target = {int(k): v for k, v in YOLO(str(args.weights)).names.items()}
    target_by_name = {v: i for i, v in target.items()}
    lvis_names = parse_names(args.lvis / "data.yaml")

    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = Counter()
    totals = {}

    def add(image: Path, label: Path, split: str, mapping):
        rows = []
        if label.exists():
            for line in label.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) != 5:
                    continue
                name = lvis_names.get(int(parts[0])) if mapping == "lvis" else COCO[int(parts[0])]
                target_name = mapping[name] if mapping != "lvis" else (name if name in target_by_name else ALIASES.get(name))
                if target_name not in target_by_name:
                    continue
                rows.append(f"{target_by_name[target_name]} {' '.join(parts[1:])}")
        if not image.exists():
            return 0
        prefix = "lvis_" if mapping == "lvis" else "coco_"
        link(image, args.output / "images" / split / (prefix + image.name))
        (args.output / "labels" / split / (prefix + image.stem + ".txt")).write_text(
            ("\n".join(rows) + "\n") if rows else "", encoding="utf-8")
        for row in rows:
            stats[(split, int(row.split()[0]))] += 1
        return len(rows)

    lvis_train = sorted((args.lvis / "images" / "train").glob("*.*"))
    rng = random.Random(42)
    rng.shuffle(lvis_train)
    val = set(lvis_train[::10])
    for image in lvis_train:
        split = "val" if image in val else "train"
        add(image, args.lvis / "labels" / "train" / (image.stem + ".txt"), split, "lvis")
    for image in sorted((args.lvis / "images" / "test").glob("*.*")):
        add(image, args.lvis / "labels" / "test" / (image.stem + ".txt"), "test", "lvis")
    for image in sorted((args.coco / "images").glob("*.*")):
        add(image, args.coco / "labels" / (image.stem + ".txt"), "train", {n: COCO_TO[n] for n in COCO})

    for split in ("train", "val", "test"):
        images = list((args.output / "images" / split).glob("*.*"))
        totals[split] = {"images": len(images), "boxes": sum(stats[(split, i)] for i in target)}
    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    for i, name in target.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({
        "classes": len(target), "splits": totals,
        "per_class": {target[i]: {"train": stats[("train", i)], "val": stats[("val", i)], "test": stats[("test", i)]} for i in target},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"classes": len(target), "splits": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
