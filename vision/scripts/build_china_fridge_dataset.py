# -*- coding: utf-8 -*-
"""Build a merged Chinese-fridge training set from FoodInsSeg + LVIS produce.

Both source datasets live outside the repository. Images are hard-linked into a
new dataset directory to avoid duplicating several GB.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import Counter
from pathlib import Path

FOODINSSEG_EXTRAS = [
    "cantaloupe", "chili", "garlic", "ginger", "mandarin", "onion",
    "papaya", "persimmon", "potato", "sweet_potato", "zucchini", "pea",
    "apricot", "date",
]

LVIS_TO_UNIFIED = {
    "almond": None,
    "apple": "apple",
    "apricot": "apricot",
    "artichoke": None,
    "asparagus": "asparagus",
    "avocado": "avocado",
    "banana": "banana",
    "bean curd/tofu": "tofu",
    "bell pepper/capsicum": "bell_pepper",
    "blackberry": None,
    "blueberry": "blueberry",
    "broccoli": "broccoli",
    "brussels sprouts": None,
    "cantaloup/cantaloupe": "cantaloupe",
    "carrot": "carrot",
    "cauliflower": "cauliflower",
    "cayenne/cayenne spice/cayenne pepper/cayenne pepper spice/red pepper/red pepper": None,
    "celery": "celery",
    "cherry": "cherry",
    "chickpea/garbanzo": None,
    "chili/chili vegetable/chili pepper/chili pepper vegetable/chilli/chilli vegetable/chilly/chilly": "chili",
    "clementine": None,
    "coconut/cocoanut": None,
    "edible corn/corn/maize": "corn",
    "cucumber/cuke": "cucumber",
    "date/date fruit": "date",
    "eggplant/aubergine": "eggplant",
    "fig/fig fruit": None,
    "garlic/ail": "garlic",
    "ginger/gingerroot": "ginger",
    "Strawberry": "strawberry",
    "gourd": None,
    "grape": "grape",
    "green bean": "green_bean",
    "green onion/spring onion/scallion": "scallion",
    "Tomato": "tomato",
    "kiwi fruit": "kiwi",
    "lemon": "lemon",
    "lettuce": "lettuce",
    "lime": None,
    "mandarin orange": "mandarin",
    "melon": "melon",
    "mushroom": "mushroom",
    "onion": "onion",
    "orange/orange fruit": "orange",
    "papaya": "papaya",
    "pea/pea food": "pea",
    "peach": "peach",
    "pear": "pear",
    "persimmon": "persimmon",
    "pickle": None,
    "pineapple": "pineapple",
    "potato": "potato",
    "prune": None,
    "pumpkin": "pumpkin",
    "radish/daikon": "radish",
    "raspberry": None,
    "strawberry": "strawberry",
    "sweet potato": "sweet_potato",
    "tomato": "tomato",
    "turnip": None,
    "watermelon": "watermelon",
    "zucchini/courgette": "zucchini",
}


def parse_names(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    in_names = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "names:":
            in_names = True
            continue
        if in_names and ":" in line:
            key, value = line.split(":", 1)
            names[int(key.strip())] = value.strip()
    return names


def hardlink(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def add_split(images, src_labels: Path, split: str, prefix: str,
              out: Path, src_names: dict[int, str], mapping: dict[str, str | None],
              class_ids: dict[str, int], stats: Counter) -> tuple[int, int]:
    kept_images = 0
    kept_boxes = 0
    for image in images:
        label = src_labels / (image.stem + ".txt")
        rows = []
        if label.exists():
            for line in label.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) != 5:
                    continue
                name = src_names.get(int(parts[0]))
                if name is None:
                    continue
                unified = mapping.get(name)
                if unified is None:
                    continue
                rows.append((class_ids[unified], parts[1:]))
        name_prefix = "fis_" if prefix == "fis" else "lvis_"
        dst_image = out / "images" / split / (name_prefix + image.name)
        dst_label = out / "labels" / split / (name_prefix + image.stem + ".txt")
        hardlink(image, dst_image)
        dst_label.parent.mkdir(parents=True, exist_ok=True)
        dst_label.write_text(
            "\n".join(f"{cid} {' '.join(values)}" for cid, values in rows) + ("\n" if rows else ""),
            encoding="utf-8",
        )
        kept_images += 1
        kept_boxes += len(rows)
        for cid, _ in rows:
            stats[(split, cid)] += 1
    return kept_images, kept_boxes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--foodinsseg", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\FoodInsSeg"))
    parser.add_argument("--lvis", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\fruits_vegetables_lvis_full"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_v1"))
    parser.add_argument("--config", type=Path, default=Path("configs/china_fridge_classes_v1.json"))
    args = parser.parse_args()

    fis_names = parse_names(args.foodinsseg / "fridge_ingredients_data.yaml")
    lvis_names = parse_names(args.lvis / "data.yaml")

    unified = [fis_names[i] for i in sorted(fis_names)]
    for name in FOODINSSEG_EXTRAS:
        if name not in unified:
            unified.append(name)
    class_ids = {name: i for i, name in enumerate(unified)}

    fis_mapping = {name: (name if name in class_ids else None) for name in fis_names.values()}
    # FoodInsSeg names are already the canonical English names.
    for name in fis_names.values():
        fis_mapping[name] = name

    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = Counter()
    totals = {}

    def source_images(root: Path) -> list[Path]:
        return sorted(p for p in root.iterdir() if p.is_file())

    fis_train_all = source_images(args.foodinsseg / "images" / "train")
    lvis_train_all = source_images(args.lvis / "images" / "train")
    # Hold out every 10th training image for validation. Test splits stay untouched.
    fis_val = fis_train_all[::10]
    fis_train = [p for i, p in enumerate(fis_train_all) if i % 10]
    lvis_val = lvis_train_all[::10]
    lvis_train = [p for i, p in enumerate(lvis_train_all) if i % 10]

    jobs = [
        ("train", fis_train, args.foodinsseg / "labels" / "train", "fis", fis_names, fis_mapping),
        ("train", lvis_train, args.lvis / "labels" / "train", "lvis", lvis_names, LVIS_TO_UNIFIED),
        ("val", fis_val, args.foodinsseg / "labels" / "train", "fis", fis_names, fis_mapping),
        ("val", lvis_val, args.lvis / "labels" / "train", "lvis", lvis_names, LVIS_TO_UNIFIED),
        ("test", source_images(args.foodinsseg / "images" / "test"), args.foodinsseg / "labels" / "test", "fis", fis_names, fis_mapping),
        ("test", source_images(args.lvis / "images" / "test"), args.lvis / "labels" / "test", "lvis", lvis_names, LVIS_TO_UNIFIED),
    ]
    for split, images, labels, prefix, names, mapping in jobs:
        imgs, boxes = add_split(images, labels, split, prefix, args.output, names, mapping, class_ids, stats)
        key = f"{prefix}_images"
        box_key = f"{prefix}_boxes"
        totals.setdefault(split, {
            "fis_images": 0, "fis_boxes": 0, "lvis_images": 0, "lvis_boxes": 0,
            "images": 0, "boxes": 0,
        })
        totals[split][key] += imgs
        totals[split][box_key] += boxes
        totals[split]["images"] += imgs
        totals[split]["boxes"] += boxes

    yaml_lines = [
        f"path: {args.output.as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    for i, name in enumerate(unified):
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")

    config = {
        "version": "2026-10-31",
        "class_count": len(unified),
        "classes": {str(i): name for i, name in enumerate(unified)},
        "sources": {
            "FoodInsSeg": "CC BY-NC-SA 4.0, non-commercial research only",
            "LVIS produce subset": "see upstream LVIS/COCO terms",
        },
    }
    args.config.parent.mkdir(parents=True, exist_ok=True)
    args.config.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "output": str(args.output),
        "classes": len(unified),
        "splits": totals,
        "per_class": {
            unified[cid]: {
                "train": stats[("train", cid)],
                "val": stats[("val", cid)],
                "test": stats[("test", cid)],
            }
            for cid in range(len(unified))
        },
    }
    (args.output / "build_stats.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("output", "classes", "splits")}, ensure_ascii=False, indent=2))
    print("config", args.config)


if __name__ == "__main__":
    main()
