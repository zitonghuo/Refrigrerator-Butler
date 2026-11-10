# -*- coding: utf-8 -*-
"""Evaluate a YOLO seg model on kitchen (COCO) and DFV16 (YOLO boxes)."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml
from ultralytics import YOLO

KITCHEN = Path(r"E:\fridge-keeper-datasets\datasets\kitchen_fruit_veg_v1")
DFV = Path(r"E:\fridge-keeper-datasets\datasets\dfv16_v1\test")
DFV_MAP = {0: 1, 1: 1, 2: 4, 3: 5, 4: 16, 5: 17, 6: 19, 7: 25, 8: 26, 10: 32, 11: 36, 12: 7, 14: 39, 15: 44}


def iou(a, b):
    l, t = max(a[0], b[0]), max(a[1], b[1])
    r, btm = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, r - l) * max(0, btm - t)
    aa = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    bb = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return inter / (aa + bb - inter) if aa + bb - inter else 0


def evaluate(model, records, conf=0.15):
    gt = matched = correct = preds = 0
    per_class = Counter()
    for p, boxes in records:
        res = model.predict(source=str(p), conf=conf, imgsz=640, verbose=False, device="0")[0]
        H, W = res.orig_shape
        plist = [] if res.boxes is None else [
            (int(b.cls), [float(v) for v in b.xyxy[0].tolist()]) for b in res.boxes
        ]
        plist = [(c, [x1 / W, y1 / H, x2 / W, y2 / H]) for c, (x1, y1, x2, y2) in plist]
        used = set()
        for target, bb in boxes:
            best, bi = 0.0, None
            for j, (cid, b) in enumerate(plist):
                if j in used:
                    continue
                ov = iou(bb, b)
                if ov > best:
                    best, bi = ov, j
            per_class[target, "gt"] += 1
            if bi is not None and best >= 0.5:
                used.add(bi)
                matched += 1
                per_class[target, "match"] += 1
                if plist[bi][0] == target:
                    correct += 1
                    per_class[target, "ok"] += 1
        gt += len(boxes)
        preds += len(plist)
    return {
        "images": len(records), "gt": gt, "matched": matched, "correct": correct,
        "recall": matched / gt if gt else 0, "class_acc": correct / matched if matched else 0,
        "e2e": correct / gt if gt else 0, "fp_per_image": (preds - matched) / len(records) if records else 0,
    }


def kitchen_records():
    j = json.loads((KITCHEN / "coco" / "annotations.json").read_text(encoding="utf-8"))
    alias = {"apple": 1, "banana": 5, "bell_pepper_green": 7, "bell_pepper_red": 7, "carrot": 11,
             "cucumber": 17, "grape": 22, "lemon": 26, "onion": 31, "orange": 32, "peach": 35,
             "potato": 39, "strawberry": 42, "tomato": 44}
    cat = {c["id"]: c["name"] for c in j["categories"]}
    imgs = {x["id"]: x for x in j["images"]}
    by = {}
    for a in j["annotations"]:
        by.setdefault(a["image_id"], []).append(a)
    out = []
    for iid, anns in by.items():
        im = imgs[iid]
        boxes = []
        for a in anns:
            x, y, w, h = a["bbox"]
            boxes.append((alias[cat[a["category_id"]]], [x / im["width"], y / im["height"],
                                                         (x + w) / im["width"], (y + h) / im["height"]]))
        out.append((KITCHEN / im["file_name"], boxes))
    return out


def dfv_records():
    out = []
    for p in sorted((DFV / "images").glob("*.jpg")):
        lab = DFV / "labels" / (p.stem + ".txt")
        if not lab.exists():
            continue
        boxes = []
        for line in lab.read_text().splitlines():
            if not line.strip():
                continue
            q = line.split()
            cid = int(q[0])
            if cid not in DFV_MAP:
                continue
            cx, cy, w, h = map(float, q[1:5])
            boxes.append((DFV_MAP[cid], [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]))
        if boxes:
            out.append((p, boxes))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", required=True)
    ap.add_argument("--out", default=r"E:\Refrigrerator-Butler\Refrigrerator-Butler\vision\outputs\real_eval.json")
    args = ap.parse_args()
    model = YOLO(args.weights)
    result = {"weights": args.weights, "kitchen": evaluate(model, kitchen_records()), "dfv16": evaluate(model, dfv_records())}
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

