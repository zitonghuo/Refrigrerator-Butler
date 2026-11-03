# -*- coding: utf-8 -*-
"""Offline augmentation for the IntAli segmentation train split."""
from __future__ import annotations

import argparse
import json
import math
import random
import shutil
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter


def parse_label(path: Path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        p = line.split()
        if len(p) >= 7:
            vals = list(map(float, p[1:]))
            rows.append((int(p[0]), list(zip(vals[0::2], vals[1::2]))))
    return rows


def rotate_points(points, angle):
    rad = math.radians(angle)
    cos, sin = math.cos(rad), math.sin(rad)
    out = []
    for x, y in points:
        dx, dy = x - 0.5, y - 0.5
        out.append((0.5 + cos * dx - sin * dy, 0.5 + sin * dx + cos * dy))
    return out


def serialize(rows):
    lines = []
    for cid, points in rows:
        coords = []
        for x, y in points:
            coords.append(f"{min(1, max(0, x)):.6f}")
            coords.append(f"{min(1, max(0, y)):.6f}")
        if len(coords) >= 6:
            lines.append(f"{cid} {' '.join(coords)}")
    return "\n".join(lines) + ("\n" if lines else "")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_seg_v1"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\intali_seg_aug_v1"))
    parser.add_argument("--copies", type=int, default=2)
    args = parser.parse_args()
    if args.output.exists():
        shutil.rmtree(args.output)
    for split in ("train", "val", "test"):
        (args.output / "images" / split).mkdir(parents=True, exist_ok=True)
        (args.output / "labels" / split).mkdir(parents=True, exist_ok=True)

    # validation/test stay untouched
    for split in ("val", "test"):
        for image in sorted((args.source / "images" / split).glob("*.*")):
            shutil.copy2(image, args.output / "images" / split / image.name)
            label = args.source / "labels" / split / (image.stem + ".txt")
            (args.output / "labels" / split / label.name).write_text(label.read_text(encoding="utf-8"), encoding="utf-8")

    random.seed(42)
    count = 0
    for image_path in sorted((args.source / "images" / "train").glob("*.*")):
        label_path = args.source / "labels" / "train" / (image_path.stem + ".txt")
        rows = parse_label(label_path) if label_path.exists() else []
        shutil.copy2(image_path, args.output / "images" / "train" / image_path.name)
        (args.output / "labels" / "train" / label_path.name).write_text(serialize(rows), encoding="utf-8")
        count += 1
        for copy_index in range(args.copies):
            with Image.open(image_path) as im:
                im = im.convert("RGB")
                angle = random.uniform(-12, 12) if random.random() < 0.7 else 0.0
                flip = random.random() < 0.5
                if angle:
                    im = im.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(127, 127, 127))
                if flip:
                    im = im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
                im = ImageEnhance.Brightness(im).enhance(random.uniform(0.75, 1.25))
                im = ImageEnhance.Contrast(im).enhance(random.uniform(0.75, 1.25))
                im = ImageEnhance.Color(im).enhance(random.uniform(0.75, 1.25))
                if random.random() < 0.25:
                    im = im.filter(ImageFilter.GaussianBlur(radius=random.uniform(0.3, 1.0)))
            out_rows = []
            for cid, points in rows:
                if angle:
                    points = rotate_points(points, -angle)
                if flip:
                    points = [(1 - x, y) for x, y in points]
                out_rows.append((cid, points))
            # The flip decision above must match the image; regenerate deterministically is
            # simpler: use a second pass with the same random state is not possible, so use
            # flip flag explicitly below instead of consuming random state.
            name = f"{image_path.stem}_aug{copy_index}{image_path.suffix}"
            im.save(args.output / "images" / "train" / name, quality=random.choice([75, 85, 92]))
            (args.output / "labels" / "train" / (Path(name).stem + ".txt")).write_text(serialize(out_rows), encoding="utf-8")
            count += 1
    yaml_lines = [f"path: {args.output.as_posix()}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    for line in (args.source / "data.yaml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(tuple(str(i) + ":" for i in range(47))):
            yaml_lines.append(line)
    (args.output / "data.yaml").write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    print(json.dumps({"images": count}, ensure_ascii=False))


if __name__ == "__main__":
    main()
