# -*- coding: utf-8 -*-
"""Mix target-style IntAli produce with LVIS/COCO raw produce for fine-tuning."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import yaml
from ultralytics import YOLO


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
    parser.add_argument("--intali", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_produce_v1"))
    parser.add_argument("--style", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\raw_style_v1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\raw_mixed_v1"))
    parser.add_argument("--intali-repeat", type=int, default=2)
    args = parser.parse_args()

    target = {int(k): v for k, v in YOLO(str(args.weights)).names.items()}
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    stats = Counter()
    totals = {}
    for split in ("train", "val"):
        count = 0
        # target-style data, optionally repeated so it is not drowned out
        repeat = args.intali_repeat if split == "train" else 1
        for copy_index in range(repeat):
            for image in sorted((args.intali / "images" / split).glob("*.*")):
                prefix = f"intali{copy_index}_"
                link(image, args.output / "images" / split / (prefix + image.name))
                label = args.intali / "labels" / split / (image.stem + ".txt")
                (args.output / "labels" / split / (prefix + image.stem + ".txt")).write_text(
                    label.read_text(encoding="utf-8") if label.exists() else "", encoding="utf-8")
                count += 1
        for image in sorted((args.style / "images" / split).glob("*.*")):
            link(image, args.output / "images" / split / ("style_" + image.name))
            label = args.style / "labels" / split / (image.stem + ".txt")
            (args.output / "labels" / split / ("style_" + image.stem + ".txt")).write_text(
                label.read_text(encoding="utf-8") if label.exists() else "", encoding="utf-8")
            count += 1
        totals[split] = count

    for split in ("train", "val"):
        for label in (args.output / "labels" / split).glob("*.txt"):
            for line in label.read_text(encoding="utf-8").splitlines():
                if len(line.split()) == 5:
                    stats[int(line.split()[0])] += 1
    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "names:"]
    for i, name in target.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({
        "splits": totals, "per_class": {target[i]: stats[i] for i in target},
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"splits": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
