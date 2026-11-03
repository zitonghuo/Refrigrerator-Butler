# -*- coding: utf-8 -*-
"""Build a mixed segmentation dataset: IntAli masks + LVIS/COCO box polygons."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import yaml
from ultralytics import YOLO


def place(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def box_polygon(values):
    cx, cy, w, h = map(float, values)
    x1, y1 = cx - w / 2, cy - h / 2
    x2, y2 = cx + w / 2, cy + h / 2
    return f"{x1:.6f} {y1:.6f} {x2:.6f} {y1:.6f} {x2:.6f} {y2:.6f} {x1:.6f} {y2:.6f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intali", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_produce_seg_v1"))
    parser.add_argument("--style", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\raw_style_v1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_cn_v2.pt"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\raw_mixed_seg_v1"))
    parser.add_argument("--intali-repeat", type=int, default=2)
    args = parser.parse_args()
    target = {int(k): v for k, v in YOLO(str(args.weights)).names.items()}
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    totals = {}
    for split in ("train", "val"):
        count = 0
        repeat = args.intali_repeat if split == "train" else 1
        for copy_index in range(repeat):
            for image in sorted((args.intali / "images" / split).glob("*.*")):
                prefix = f"intali{copy_index}_"
                place(image, args.output / "images" / split / (prefix + image.name))
                label = args.intali / "labels" / split / (image.stem + ".txt")
                (args.output / "labels" / split / (prefix + image.stem + ".txt")).write_text(
                    label.read_text(encoding="utf-8") if label.exists() else "", encoding="utf-8")
                count += 1
        for image in sorted((args.style / "images" / split).glob("*.*")):
            prefix = "style_"
            place(image, args.output / "images" / split / (prefix + image.name))
            src = args.style / "labels" / split / (image.stem + ".txt")
            rows = []
            if src.exists():
                for line in src.read_text(encoding="utf-8").splitlines():
                    p = line.split()
                    if len(p) == 5:
                        rows.append(f"{p[0]} {box_polygon(p[1:])}")
            (args.output / "labels" / split / (prefix + image.stem + ".txt")).write_text(
                ("\n".join(rows) + "\n") if rows else "", encoding="utf-8")
            count += 1
        totals[split] = count

    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "names:"]
    for i, name in target.items():
        yaml_lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({"splits": totals}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"splits": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
