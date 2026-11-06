# -*- coding: utf-8 -*-
"""Merge IntAli and AICook produce segmentation data for training."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

import yaml


def place(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--intali", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_produce_seg_v1"))
    parser.add_argument("--aicook", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\aicook_produce_v1"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\raw_mixed_seg_v2"))
    args = parser.parse_args()
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    totals = {}
    for split in ("train", "val", "test"):
        n = 0
        sources = [("intali", args.intali, split)]
        if split == "train":
            sources.append(("aicook", args.aicook, "train"))
        elif split == "val":
            sources.append(("aicook", args.aicook, "valid"))
        for prefix, root, source_split in sources:
            for image in sorted((root / "images" / source_split).glob("*.*")):
                place(image, args.output / "images" / split / (prefix + "_" + image.name))
                label = root / "labels" / source_split / (image.stem + ".txt")
                (args.output / "labels" / split / (prefix + "_" + image.stem + ".txt")).write_text(
                    label.read_text(encoding="utf-8") if label.exists() else "", encoding="utf-8")
                n += 1
        totals[split] = n

    source_yaml = yaml.safe_load((args.intali / "data.yaml").read_text(encoding="utf-8"))
    names = source_yaml["names"]
    lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    if isinstance(names, dict):
        for i in sorted(names):
            lines.append(f"  {i}: {names[i]}")
    else:
        for i, name in enumerate(names):
            lines.append(f"  {i}: {name}")
    (args.output / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.output / "build_stats.json").write_text(json.dumps({"splits": totals}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"splits": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
