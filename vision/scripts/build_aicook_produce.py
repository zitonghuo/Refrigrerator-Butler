# -*- coding: utf-8 -*-
"""Convert AICook boxes to YOLO-seg labels for supported produce classes."""
from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from pathlib import Path

import yaml
from ultralytics import YOLO

MAP = {
    "apple": "apple",
    "banana": "banana",
    "blueberries": "blueberry",
    "carrot": "carrot",
    "corn": "edible corn/corn/maize",
    "green_beans": "green bean",
    "mushrooms": "mushroom",
    "onion": "onion",
    "potato": "potato",
    "strawberries": "strawberry",
    "sweet_potato": "sweet potato",
    "tomato": "tomato",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\aicook"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\aicook_produce_v1"))
    args = parser.parse_args()

    target = {int(k): v for k, v in YOLO(str(args.weights)).names.items()}
    target_by_name = {v: i for i, v in target.items()}
    source_yaml = yaml.safe_load((args.source / "data.yaml").read_text(encoding="utf-8"))
    source_names = source_yaml["names"]
    if isinstance(source_names, dict):
        source_names = [source_names[i] for i in sorted(source_names)]
    class_map = {i: target_by_name[MAP[n]] for i, n in enumerate(source_names) if n in MAP and MAP[n] in target_by_name}
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "valid", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)
    stats = Counter()
    totals = {}
    for split in ("train", "valid", "test"):
        kept_images = kept_boxes = 0
        for label in sorted((args.source / split / "labels").glob("*.txt")):
            rows = []
            for line in label.read_text(encoding="utf-8").splitlines():
                p = line.split()
                if len(p) != 5 or int(p[0]) not in class_map:
                    continue
                cid = class_map[int(p[0])]
                cx, cy, w, h = map(float, p[1:])
                if w < 0.01 or h < 0.01:
                    continue
                x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
                rows.append(f"{cid} {x1:.6f} {y1:.6f} {x2:.6f} {y1:.6f} {x2:.6f} {y2:.6f} {x1:.6f} {y2:.6f}")
            if not rows:
                continue
            image = args.source / split / "images" / (label.stem + ".jpg")
            if not image.exists():
                image = args.source / split / "images" / (label.stem + ".png")
            if not image.exists():
                continue
            shutil.copy2(image, args.output / "images" / split / image.name)
            (args.output / "labels" / split / label.name).write_text("\n".join(rows) + "\n", encoding="utf-8")
            kept_images += 1
            kept_boxes += len(rows)
            for row in rows:
                stats[int(row.split()[0])] += 1
        totals[split] = {"images": kept_images, "boxes": kept_boxes}

    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/valid", "test: images/test", "names:"]
    for i, name in target.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({"splits": totals, "per_class": {target[i]: stats[i] for i in target}}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"splits": totals, "classes": len(class_map)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
