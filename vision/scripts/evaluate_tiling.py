# -*- coding: utf-8 -*-
"""Compare full-image inference with simple overlapping tiling."""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path

import torch
import yaml
from PIL import Image
from torchvision.ops import nms
from ultralytics import YOLO


def parse_names(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data["names"].items()}


def yolo_to_xyxy(values):
    cx, cy, w, h = values
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def iou(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union else 0.0


def merge(preds):
    """Class-aware NMS over mapped full-image boxes."""
    by_class = defaultdict(list)
    for label, box, score in preds:
        by_class[label].append((box, score))
    result = []
    for label, items in by_class.items():
        boxes = torch.tensor([i[0] for i in items], dtype=torch.float32)
        scores = torch.tensor([i[1] for i in items], dtype=torch.float32)
        keep = nms(boxes, scores, 0.5)
        for k in keep.tolist():
            result.append((label, items[k][0], items[k][1]))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_produce_v1"))
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--conf", type=float, default=0.10)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--tile", type=int, default=640)
    parser.add_argument("--overlap", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--device", default="0")
    parser.add_argument("--output", type=Path, default=Path("outputs/tiling_eval.json"))
    args = parser.parse_args()

    names = parse_names(args.dataset / "data.yaml")
    model = YOLO(str(args.weights))
    images = sorted((args.dataset / "images" / "test").glob("*.*"))
    if args.limit:
        images = images[: args.limit]

    def predict_boxes(source):
        result = model.predict(source=source, conf=args.conf, iou=0.5, imgsz=args.imgsz,
                               device=args.device, verbose=False)[0]
        boxes = []
        if result.boxes is not None:
            for box in result.boxes:
                cid = int(box.cls.item())
                xyxy = [float(v) for v in box.xyxy[0].tolist()]
                boxes.append((names[cid], xyxy, float(box.conf.item())))
        return boxes

    def tiles(width, height):
        stride = max(1, int(args.tile * (1 - args.overlap)))
        xs = list(range(0, max(1, width - args.tile + 1), stride)) or [0]
        ys = list(range(0, max(1, height - args.tile + 1), stride)) or [0]
        if xs[-1] + args.tile < width:
            xs.append(width - args.tile)
        if ys[-1] + args.tile < height:
            ys.append(height - args.tile)
        xs = [max(0, x) for x in xs][:4]
        ys = [max(0, y) for y in ys][:4]
        return [(x, y, min(width, x + args.tile), min(height, y + args.tile)) for y in ys for x in xs]

    result = {"full": {"gt": 0, "matched": 0, "correct": 0, "pred": 0},
              "tiled": {"gt": 0, "matched": 0, "correct": 0, "pred": 0}}
    for image_path in images:
        label_path = args.dataset / "labels" / "test" / (image_path.stem + ".txt")
        gt = []
        if label_path.exists():
            for line in label_path.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 5:
                    gt.append((names[int(parts[0])], yolo_to_xyxy(list(map(float, parts[1:])))))

        full_preds = predict_boxes(str(image_path))
        with Image.open(image_path) as im:
            width, height = im.size
            tiled_preds = []
            for left, top, right, bottom in tiles(width, height):
                tile = im.crop((left, top, right, bottom))
                for label, box, score in predict_boxes(tile):
                    tiled_preds.append((label, [box[0] + left, box[1] + top, box[2] + left, box[3] + top], score))
        tiled_preds = merge(tiled_preds)

        for key, preds in (("full", full_preds), ("tiled", tiled_preds)):
            matched = set()
            correct = set()
            normalized = [(label, [box[0] / width, box[1] / height, box[2] / width, box[3] / height], score)
                          for label, box, score in preds]
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
            result[key]["gt"] += len(gt)
            result[key]["matched"] += len(matched)
            result[key]["correct"] += len(correct)
            result[key]["pred"] += len(preds)

    for key in ("full", "tiled"):
        s = result[key]
        s["recall"] = round(s["matched"] / s["gt"], 4) if s["gt"] else None
        s["class_accuracy"] = round(s["correct"] / s["matched"], 4) if s["matched"] else None
        s["end_to_end"] = round(s["correct"] / s["gt"], 4) if s["gt"] else None
        s["fp_per_image"] = round((s["pred"] - s["matched"]) / len(images), 2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"settings": vars(args), "images": len(images), "result": result}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"images": len(images), "result": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
