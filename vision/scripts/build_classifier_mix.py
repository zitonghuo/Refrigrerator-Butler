# -*- coding: utf-8 -*-
"""Mix Fruits-360 single-item crops with IntAli real-background crops."""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


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
    parser.add_argument("--fruits", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\fruits360_47subset"))
    parser.add_argument("--intali", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_crops_v1"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\classifier_mix_v1"))
    parser.add_argument("--intali-repeat", type=int, default=3)
    args = parser.parse_args()
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val", "test"):
        (args.output / split).mkdir(parents=True, exist_ok=True)

    for split in ("train", "val"):
        for folder in (args.fruits / split).iterdir():
            if not folder.is_dir():
                continue
            for image in folder.glob("*.jpg"):
                place(image, args.output / split / folder.name / ("fruits_" + image.name))
        repeat = args.intali_repeat if split == "train" else 1
        for copy_index in range(repeat):
            for folder in (args.intali / split).iterdir():
                if not folder.is_dir():
                    continue
                for image in folder.glob("*.jpg"):
                    place(image, args.output / split / folder.name / (f"intali{copy_index}_" + image.name))
    for folder in (args.intali / "test").iterdir():
        if not folder.is_dir():
            continue
        for image in folder.glob("*.jpg"):
            place(image, args.output / "test" / folder.name / ("intali_" + image.name))
    print("built", args.output)


if __name__ == "__main__":
    main()
