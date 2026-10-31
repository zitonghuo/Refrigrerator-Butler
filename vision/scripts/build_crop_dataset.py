# -*- coding: utf-8 -*-
"""Build a 47-class crop classification dataset from detector boxes."""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from PIL import Image, ImageOps


def parse_names(path: Path) -> dict[int, str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data["names"].items()}


def safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:48]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_produce_v1"))
    parser.add_argument("--output", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_produce_crops_v1"))
    parser.add_argument("--size", type=int, default=256)
    parser.add_argument("--train-per-class", type=int, default=1200)
    parser.add_argument("--val-per-class", type=int, default=300)
    parser.add_argument("--test-per-class", type=int, default=300)
    args = parser.parse_args()

    names = parse_names(args.dataset / "data.yaml")
    folders = {i: f"{i:02d}_{safe(name)}" for i, name in names.items()}
    if args.output.exists():
        # keep it simple: rebuild only the crop tree
        for split in ("train", "val", "test"):
            target = args.output / split
            if target.exists():
                import shutil
                shutil.rmtree(target)

    limits = {"train": args.train_per_class, "val": args.val_per_class, "test": args.test_per_class}
    meta = {"classes": {str(i): name for i, name in names.items()}, "folders": folders, "splits": {}}

    for split in ("train", "val", "test"):
        entries = []
        for label in sorted((args.dataset / "labels" / split).glob("*.txt")):
            image_path = args.dataset / "images" / split / (label.stem + ".jpg")
            if not image_path.exists():
                candidates = list((args.dataset / "images" / split).glob(label.stem + ".*"))
                if not candidates:
                    continue
                image_path = candidates[0]
            with Image.open(image_path) as im:
                width, height = im.size
            rows = []
            for line in label.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) != 5:
                    continue
                cid = int(parts[0])
                cx, cy, w, h = map(float, parts[1:])
                x1, y1 = (cx - w / 2) * width, (cy - h / 2) * height
                x2, y2 = (cx + w / 2) * width, (cy + h / 2) * height
                if x2 - x1 < 8 or y2 - y1 < 8:
                    continue
                rows.append((cid, x1, y1, x2, y2))
            if rows:
                entries.append((image_path, rows))

        rng = random.Random(42)
        by_class = defaultdict(list)
        for image_path, rows in entries:
            for row in rows:
                by_class[row[0]].append((image_path, row))
        chosen = []
        for cid, items in by_class.items():
            rng.shuffle(items)
            chosen.extend(items[: limits[split]])
        rng.shuffle(chosen)

        counts = Counter()
        for index, (image_path, (cid, x1, y1, x2, y2)) in enumerate(chosen):
            with Image.open(image_path) as im:
                im = im.convert("RGB")
                width, height = im.size
                pad_x = (x2 - x1) * 0.12
                pad_y = (y2 - y1) * 0.12
                left = max(0, int(x1 - pad_x))
                top = max(0, int(y1 - pad_y))
                right = min(width, int(x2 + pad_x))
                bottom = min(height, int(y2 + pad_y))
                if right <= left or bottom <= top:
                    continue
                crop = im.crop((left, top, right, bottom))
                crop = ImageOps.pad(crop, (args.size, args.size), color=(127, 127, 127), method=Image.Resampling.BILINEAR)
                folder = args.output / split / folders[cid]
                folder.mkdir(parents=True, exist_ok=True)
                crop.save(folder / f"{index:06d}.jpg", quality=90)
                counts[cid] += 1
        meta["splits"][split] = {
            "images": len(entries),
            "crops": sum(counts.values()),
            "per_class": {names[cid]: counts[cid] for cid in names},
        }
        print(split, sum(counts.values()), "crops", len(entries), "source images")

    (args.output / "classes.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("written", args.output)


if __name__ == "__main__":
    main()
