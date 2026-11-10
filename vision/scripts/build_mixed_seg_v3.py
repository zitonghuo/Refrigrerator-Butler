# -*- coding: utf-8 -*-
"""Merge the existing v2 dataset with DFV16 SAM-seg labels."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import yaml

BASE = Path(r"E:\fridge-keeper-datasets\datasets")
V2 = BASE / "raw_mixed_seg_v2"
DFV = BASE / "dfv16_seg_v1"
OUT = BASE / "raw_mixed_seg_v3"


def put(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        return
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def add_split(split: str, image_dir: Path, label_dir: Path, prefix: str, stats: dict):
    n = 0
    for img in sorted(image_dir.glob("*.*")):
        lab = label_dir / (img.stem + ".txt")
        if not lab.exists():
            continue
        name = (prefix + img.name) if prefix else img.name
        put(img, OUT / "images" / split / name)
        shutil.copy2(lab, OUT / "labels" / split / (Path(name).stem + ".txt"))
        n += 1
    stats[split] = stats.get(split, 0) + n
    print(split, prefix or "v2", n)


def main():
    for sub in ("images/train", "images/val", "images/test", "labels/train", "labels/val", "labels/test"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    stats = {}
    for split in ("train", "val", "test"):
        add_split(split, V2 / "images" / split, V2 / "labels" / split, "", stats)
    for split in ("train", "val"):
        add_split(split, DFV / split / "images", DFV / split / "labels", "", stats)
    cfg = yaml.safe_load((V2 / "data.yaml").read_text(encoding="utf-8"))
    cfg["path"] = str(OUT)
    cfg["train"] = "images/train"
    cfg["val"] = "images/val"
    cfg["test"] = "images/test"
    (OUT / "data.yaml").write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (OUT / "build_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
