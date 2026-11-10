# -*- coding: utf-8 -*-
"""Build the 61-class v4 dataset from raw IntAli/AICook plus DFV16 seg labels."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import cv2
import yaml

BASE = Path(r"E:\fridge-keeper-datasets")
INTALI = BASE / "kagglehub" / "datasets" / "miketrs" / "intali-food-dataset" / "versions" / "1"
AICOOK = BASE / "datasets" / "aicook"
DFV = BASE / "datasets" / "dfv16_seg_v1"
OUT = BASE / "datasets" / "raw_mixed_seg_v4"

OLD = yaml.safe_load((BASE / "datasets" / "raw_mixed_seg_v2" / "data.yaml").read_text(encoding="utf-8"))["names"]
NAMES = {int(k): v for k, v in OLD.items()}
NEW = {
    47: "egg", 48: "milk", 49: "yogurt", 50: "cheese", 51: "butter",
    52: "cream", 53: "meat", 54: "shrimp", 55: "fish", 56: "spinach",
    57: "cabbage", 58: "beet", 59: "lime", 60: "pomegranate",
}
NAMES.update(NEW)
NAME_TO_ID = {v: k for k, v in NAMES.items()}


def target_id(name: str):
    n = name.strip().lower()
    aliases = {
        "blueberries": "blueberry", "strawberries": "strawberry",
        "mushrooms": "mushroom", "cherry tomatoes": "tomato",
        "green pepper": "bell pepper/capsicum", "hot pepper": "chili/chili vegetable/chili pepper/chili pepper vegetable/chilli/chilli vegetable/chilly/chilly",
        "green peas": "pea/pea food", "sweet potato": "sweet potato",
        "green beans": "green bean", "cantaloupe": "cantaloup/cantaloupe",
        "kiwi": "kiwi fruit", "orange": "orange/orange fruit",
        "eggs": "egg", "egg": "egg",
        "milk": "milk",
        "yogurt": "yogurt",
        "cheese": "cheese", "feta cheese": "cheese", "mozzarella cheese": "cheese",
        "ricotta cheese": "cheese", "cream cheese": "cheese", "goat_cheese": "cheese",
        "butter": "butter",
        "sour cream": "cream", "heavy_cream": "cream", "whipped cream": "cream",
        "beef": "meat", "ground_beef": "meat", "ground beef": "meat",
        "pork": "meat", "pork deli": "meat", "ham": "meat", "bacon": "meat",
        "sausage": "meat", "salami": "meat", "prosciutto": "meat", "liver": "meat",
        "pate": "meat", "meat": "meat", "chicken": "meat", "chicken breast": "meat",
        "whole chicken": "meat", "chicken thighs": "meat", "canned meat": "meat",
        "shrimp": "shrimp",
        "fish": "fish", "smoked salmon": "fish",
        "spinach": "spinach", "cabbage": "cabbage", "beet": "beet",
        "lime": "lime", "pomegranate": "pomegranate",
    }
    if n in aliases:
        n = aliases[n]
    return NAME_TO_ID.get(n)


def put_image(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def add_intali():
    counts = Counter()
    for split in ("train", "test"):
        data = json.loads((INTALI / f"{split}.json").read_text(encoding="utf-8"))
        cats = {c["id"]: c["name"] for c in data["categories"]}
        by_img = {}
        for ann in data["annotations"]:
            cid = target_id(cats[ann["category_id"]])
            if cid is None:
                continue
            seg = ann.get("segmentation") or []
            if isinstance(seg, dict):
                continue
            polys = [p for p in seg if isinstance(p, list) and len(p) >= 6]
            if not polys:
                x, y, w, h = ann["bbox"]
                polys = [[x, y, x + w, y, x + w, y + h, x, y + h]]
            poly = max(polys, key=len)
            by_img.setdefault(ann["image_id"], []).append((cid, poly))
        for image in data["images"]:
            rows = []
            for cid, poly in by_img.get(image["id"], []):
                pts = [(poly[i], poly[i + 1]) for i in range(0, len(poly) - 1, 2)]
                if len(pts) < 3:
                    continue
                coords = []
                for x, y in pts:
                    coords += [f"{min(1, max(0, x / image['width'])):.6f}", f"{min(1, max(0, y / image['height'])):.6f}"]
                rows.append(f"{cid} {' '.join(coords)}")
            if not rows:
                continue
            src = INTALI / "images" / image["file_name"]
            if not src.exists():
                continue
            stem = image["file_name"].replace("/", "__")
            digest = int(hashlib.md5(stem.encode()).hexdigest()[:8], 16)
            out_split = "val" if split == "train" and digest % 10 == 0 else ("test" if split == "test" else "train")
            name = "intali_" + stem
            put_image(src, OUT / "images" / out_split / name)
            (OUT / "labels" / out_split / (Path(name).stem + ".txt")).write_text("\n".join(rows) + "\n", encoding="utf-8")
            counts[out_split] += 1
    return counts


def add_aicook():
    counts = Counter()
    cfg = yaml.safe_load((AICOOK / "data.yaml").read_text(encoding="utf-8"))
    names = {int(k): v for k, v in cfg["names"].items()} if isinstance(cfg["names"], dict) else dict(enumerate(cfg["names"]))
    for source_split, out_split in (("train", "train"), ("valid", "val")):
        for img in sorted((AICOOK / source_split / "images").glob("*.*")):
            label = AICOOK / source_split / "labels" / (img.stem + ".txt")
            if not label.exists():
                continue
            rows = []
            for line in label.read_text().splitlines():
                if not line.strip():
                    continue
                q = line.split()
                cid = target_id(names[int(q[0])])
                if cid is None:
                    continue
                cx, cy, w, h = map(float, q[1:5])
                x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
                rows.append(f"{cid} {x1:.6f} {y1:.6f} {x2:.6f} {y1:.6f} {x2:.6f} {y2:.6f} {x1:.6f} {y2:.6f}")
            if not rows:
                continue
            name = "aicook_" + img.name
            put_image(img, OUT / "images" / out_split / name)
            (OUT / "labels" / out_split / (Path(name).stem + ".txt")).write_text("\n".join(rows) + "\n", encoding="utf-8")
            counts[out_split] += 1
    return counts


def add_dfv16():
    counts = Counter()
    for split in ("train", "val"):
        for img in sorted((DFV / split / "images").glob("*.jpg")):
            label = DFV / split / "labels" / (img.stem + ".txt")
            if not label.exists():
                continue
            rows = label.read_text(encoding="utf-8")
            if not rows.strip():
                continue
            name = "dfv16_" + img.name
            put_image(img, OUT / "images" / split / name)
            (OUT / "labels" / split / (Path(name).stem + ".txt")).write_text(rows, encoding="utf-8")
            counts[split] += 1
    return counts


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    for split in ("train", "val", "test"):
        for sub in ("images", "labels"):
            (OUT / sub / split).mkdir(parents=True, exist_ok=True)
    stats = {}
    for fn in (add_intali, add_aicook, add_dfv16):
        c = fn()
        for k, v in c.items():
            stats[k] = stats.get(k, 0) + v
    lines = [f"path: {OUT.as_posix()}", "train: images/train", "val: images/val", "test: images/test", "names:"]
    lines += [f"  {i}: {NAMES[i]}" for i in sorted(NAMES)]
    (OUT / "data.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "build_stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
