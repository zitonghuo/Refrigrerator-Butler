# -*- coding: utf-8 -*-
"""Filter the merged dataset down to the 47-class produce model."""
from __future__ import annotations

import argparse
import json
import os
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


def parse_names(path: Path) -> dict[int, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data["names"].items()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_v1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_produce_v1"))
    args = parser.parse_args()

    source_names = parse_names(args.source / "data.yaml")
    model = YOLO(str(args.weights))
    target_names = {int(k): v for k, v in model.names.items()}
    target_by_name = {v: i for i, v in target_names.items()}

    # source unified name -> target produce name
    mapping = {}
    for name in source_names.values():
        target = name if name in target_by_name else ALIASES.get(name)
        if target in target_by_name:
            mapping[name] = target

    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = Counter()
    totals = {}
    for split in ("train", "val", "test"):
        images = sorted((args.source / "images" / split).glob("*.*"))
        kept_boxes = 0
        nonempty = 0
        for image in images:
            label = args.source / "labels" / split / (image.stem + ".txt")
            rows = []
            if label.exists():
                for line in label.read_text(encoding="utf-8").splitlines():
                    parts = line.split()
                    if len(parts) != 5:
                        continue
                    name = source_names.get(int(parts[0]))
                    target = mapping.get(name) if name else None
                    if target is None:
                        continue
                    rows.append(f"{target_by_name[target]} {' '.join(parts[1:])}")
            dst_image = args.output / "images" / split / image.name
            dst_label = args.output / "labels" / split / (image.stem + ".txt")
            dst_image.parent.mkdir(parents=True, exist_ok=True)
            if not dst_image.exists():
                try:
                    os.link(image, dst_image)
                except OSError:
                    shutil.copy2(image, dst_image)
            dst_label.write_text(("\n".join(rows) + "\n") if rows else "", encoding="utf-8")
            kept_boxes += len(rows)
            if rows:
                nonempty += 1
            for row in rows:
                stats[(split, int(row.split()[0]))] += 1
        totals[split] = {"images": len(images), "images_with_produce": nonempty, "boxes": kept_boxes}

    yaml_lines = [
        f"path: {args.output.as_posix()}",
        "train: images/train",
        "val: images/val",
        "test: images/test",
        "names:",
    ]
    for i, name in target_names.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({
        "classes": len(target_names),
        "mapping": mapping,
        "splits": totals,
        "per_class": {target_names[i]: {"train": stats[("train", i)], "val": stats[("val", i)], "test": stats[("test", i)]} for i in target_names},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"classes": len(target_names), "splits": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
