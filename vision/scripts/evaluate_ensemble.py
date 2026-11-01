# -*- coding: utf-8 -*-
"""Evaluate a simple two-detector union (class-aware NMS)."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch
import yaml
from torchvision.ops import nms
from ultralytics import YOLO


def parse_names(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data["names"].items()}


def xyxy(values):
    cx, cy, w, h = values
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def iou(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, right - left) * max(0.0, bottom - top)
    aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    bb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = aa + bb - inter
    return inter / union if union else 0.0


def merge(preds):
    by_class = defaultdict(list)
    for label, box, score in preds:
        by_class[label].append((box, score))
    out = []
    for label, items in by_class.items():
        boxes = torch.tensor([i[0] for i in items], dtype=torch.float32)
        scores = torch.tensor([i[1] for i in items], dtype=torch.float32)
        for k in nms(boxes, scores, 0.5).tolist():
            out.append((label, items[k][0], items[k][1]))
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_produce_v1"))
    parser.add_argument("--weights-a", type=Path, required=True)
    parser.add_argument("--weights-b", type=Path, required=True)
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--device", default="0")
    parser.add_argument("--output", type=Path, default=Path("outputs/ensemble_eval.json"))
    args = parser.parse_args()

    names = parse_names(args.dataset / "data.yaml")
    models = [YOLO(str(args.weights_a)), YOLO(str(args.weights_b))]
    images = sorted((args.dataset / "images" / "test").glob("*.*"))
    if args.limit:
        images = images[: args.limit]

    totals = {k: {"gt": 0, "matched": 0, "correct": 0, "pred": 0} for k in ("a", "b", "union")}
    for image_path in images:
        label_path = args.dataset / "labels" / "test" / (image_path.stem + ".txt")
        gt = []
        if label_path.exists():
            for line in label_path.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 5:
                    gt.append((names[int(parts[0])], xyxy(list(map(float, parts[1:])))))

        per_model = []
        for model in models:
            result = model.predict(source=str(image_path), conf=args.conf, iou=0.5,
                                   imgsz=args.imgsz, device=args.device, verbose=False)[0]
            preds = []
            if result.boxes is not None:
                for box in result.boxes:
                    preds.append((names[int(box.cls.item())], [float(v) for v in box.xyxy[0].tolist()], float(box.conf.item())))
            per_model.append(preds)

        from PIL import Image
        with Image.open(image_path) as im:
            width, height = im.size
        for key, preds in (("a", per_model[0]), ("b", per_model[1]), ("union", merge(per_model[0] + per_model[1]))):
            normalized = [(l, [b[0] / width, b[1] / height, b[2] / width, b[3] / height], s) for l, b, s in preds]
            matched, correct = set(), set()
            for label, box, _ in sorted(normalized, key=lambda x: x[2], reverse=True):
                best_i, best = None, 0.0
                for i, (_, gt_box) in enumerate(gt):
                    if i in matched:
                        continue
                    overlap = iou(box, gt_box)
                    if overlap > best:
                        best, best_i = overlap, i
                if best_i is not None and best >= 0.5:
                    matched.add(best_i)
                    if label == gt[best_i][0]:
                        correct.add(best_i)
            totals[key]["gt"] += len(gt)
            totals[key]["matched"] += len(matched)
            totals[key]["correct"] += len(correct)
            totals[key]["pred"] += len(preds)

    for key, s in totals.items():
        s["recall"] = round(s["matched"] / s["gt"], 4)
        s["class_accuracy"] = round(s["correct"] / s["matched"], 4)
        s["end_to_end"] = round(s["correct"] / s["gt"], 4)
        s["fp_per_image"] = round((s["pred"] - s["matched"]) / len(images), 2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"images": len(images), "result": totals}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"images": len(images), "result": totals}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
