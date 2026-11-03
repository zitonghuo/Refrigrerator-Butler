# -*- coding: utf-8 -*-
"""Filter Fruits-360 100x100 to the produce classes the serving model supports."""
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

def place(src, dst):
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


RULES = [
    ("Apple", "apple"),
    ("Apricot", "apricot"),
    ("Avocado", "avocado"),
    ("Banana", "banana"),
    ("Blueberry", "blueberry"),
    ("Cantaloupe", "cantaloup/cantaloupe"),
    ("Cauliflower", "cauliflower"),
    ("Cherry", "cherry"),
    ("Clementine", "mandarin orange"),
    ("Corn", "edible corn/corn/maize"),
    ("Cucumber", "cucumber/cuke"),
    ("Dates", "date/date fruit"),
    ("Eggplant", "eggplant/aubergine"),
    ("Ginger Root", "ginger/gingerroot"),
    ("Grape", "grape"),
    ("Kaki", "persimmon"),
    ("Kiwi", "kiwi fruit"),
    ("Lemon", "lemon"),
    ("Mandarine", "mandarin orange"),
    ("Melon Piel de Sapo", "melon"),
    ("Onion", "onion"),
    ("Orange", "orange/orange fruit"),
    ("Papaya", "papaya"),
    ("Peach", "peach"),
    ("Pear", "pear"),
    ("Pepper", "bell pepper/capsicum"),
    ("Pineapple", "pineapple"),
    ("Potato", "potato"),
    ("Strawberry", "strawberry"),
    ("Tangelo", "orange/orange fruit"),
    ("Tomato", "tomato"),
    ("Watermelon", "watermelon"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"C:\Users\ALIENWARE\.cache\kagglehub\datasets\ishandandekar\fruitimagedataset\versions\1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\fruits360_47subset"))
    args = parser.parse_args()

    target = {int(k): v for k, v in YOLO(str(args.weights)).names.items()}
    target_by_name = {v: i for i, v in target.items()}
    source_train = args.source / "train" / "train"
    source_test = args.source / "test" / "test"
    classes = {}
    for folder in sorted(source_train.iterdir()):
        if not folder.is_dir():
            continue
        for prefix, target_name in RULES:
            if folder.name.startswith(prefix) and target_name in target_by_name:
                classes.setdefault(target_name, []).append(folder.name)
                break
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val", "test"):
        (args.output / split).mkdir(parents=True, exist_ok=True)

    counts = Counter()
    for target_name, folders in classes.items():
        safe = target_name.split("/")[0].replace(" ", "_")
        for folder_name in folders:
            for split, src_root in (("train", source_train), ("test", source_test)):
                src = src_root / folder_name
                if not src.exists():
                    continue
                files = sorted(src.glob("*.jpg"))
                random.Random(42).shuffle(files)
                if split == "train":
                    val_count = max(1, len(files) // 10)
                    val_files = files[:val_count]
                    train_files = files[val_count:]
                    for image in val_files:
                        dst = args.output / "val" / safe / (folder_name.replace(" ", "_") + "__" + image.name)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        place(image, dst)
                    for image in train_files:
                        dst = args.output / "train" / safe / (folder_name.replace(" ", "_") + "__" + image.name)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        place(image, dst)
                    counts[(target_name, "train")] += len(train_files)
                    counts[(target_name, "val")] += len(val_files)
                else:
                    for image in files:
                        dst = args.output / "test" / safe / (folder_name.replace(" ", "_") + "__" + image.name)
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        place(image, dst)
                    counts[(target_name, "test")] += len(files)

    (args.output / "classes.json").write_text(json.dumps({
        "target_classes": list(classes), "sources": classes,
        "counts": {f"{k[0]}|{k[1]}": v for k, v in sorted(counts.items())},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "target_classes": len(classes),
        "sources": len({f for folders in classes.values() for f in folders}),
        "images": {s: sum(v for (c, ss), v in counts.items() if ss == s) for s in ("train", "val", "test")},
        "class_names": sorted(classes),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
