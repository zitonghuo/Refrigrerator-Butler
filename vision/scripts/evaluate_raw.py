# -*- coding: utf-8 -*-
"""Evaluate a raw-produce detector on a held-out split."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import yaml

from food_recognition.service import FoodRecognizer


def names(path: Path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {int(k): v for k, v in data["names"].items()}


def xyxy(v):
    cx, cy, w, h = v
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def iou(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, right - left) * max(0.0, bottom - top)
    aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    bb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (aa + bb - inter) if aa + bb - inter else 0.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--output", type=Path, default=Path("outputs/raw_produce_eval.json"))
    args = parser.parse_args()

    label_names = names(args.dataset / "data.yaml")
    recognizer = FoodRecognizer(args.weights, device=args.device, confidence_threshold=args.conf, image_size=args.imgsz)
    stats = defaultdict(lambda: {"gt": 0, "matched": 0, "correct": 0, "pred": 0})
    groups = defaultdict(lambda: {"images": 0, "gt": 0, "matched": 0, "correct": 0, "pred": 0})
    images = sorted((args.dataset / "images" / args.split).glob("*.*"))
    for image in images:
        label = args.dataset / "labels" / args.split / (image.stem + ".txt")
        gt = []
        if label.exists():
            for line in label.read_text(encoding="utf-8").splitlines():
                p = line.split()
                if len(p) == 5:
                    gt.append((label_names[int(p[0])], xyxy(list(map(float, p[1:])))))
                elif len(p) >= 7:
                    values = list(map(float, p[1:]))
                    xs, ys = values[0::2], values[1::2]
                    gt.append((label_names[int(p[0])], (min(xs), min(ys), max(xs), max(ys))))
        result = recognizer.predict_image(image)
        preds = [(c.label, [c.bbox_xyxy[0] / result.image_width, c.bbox_xyxy[1] / result.image_height,
                            c.bbox_xyxy[2] / result.image_width, c.bbox_xyxy[3] / result.image_height], c.confidence)
                 for c in result.candidates]
        matched, correct = set(), set()
        for label_name, box, _ in sorted(preds, key=lambda x: x[2], reverse=True):
            best_i, best = None, 0.0
            for i, (_, gt_box) in enumerate(gt):
                if i in matched:
                    continue
                overlap = iou(box, gt_box)
                if overlap > best:
                    best, best_i = overlap, i
            if best_i is not None and best >= 0.5:
                matched.add(best_i)
                if label_name == gt[best_i][0]:
                    correct.add(best_i)
        for i, (name, _) in enumerate(gt):
            stats[name]["gt"] += 1
            if i in matched:
                stats[name]["matched"] += 1
            if i in correct:
                stats[name]["correct"] += 1
        source = "coco" if image.name.startswith("coco_") else "lvis"
        g = groups[source]
        g["images"] += 1; g["gt"] += len(gt); g["matched"] += len(matched); g["correct"] += len(correct); g["pred"] += len(preds)

    def rate(a, b):
        return round(a / b, 4) if b else None

    total_gt = sum(v["gt"] for v in stats.values())
    total_matched = sum(v["matched"] for v in stats.values())
    total_correct = sum(v["correct"] for v in stats.values())
    report = {
        "overall": {"images": len(images), "gt": total_gt, "matched": total_matched, "correct": total_correct,
                    "recall": rate(total_matched, total_gt), "class_accuracy": rate(total_correct, total_matched),
                    "end_to_end": rate(total_correct, total_gt),
                    "fp_per_image": round(sum(v["pred"] - v["matched"] for v in groups.values()) / len(images), 2)},
        "by_source": {k: {"images": v["images"], "gt": v["gt"], "matched": v["matched"], "correct": v["correct"],
                          "recall": rate(v["matched"], v["gt"]), "class_accuracy": rate(v["correct"], v["matched"]),
                          "end_to_end": rate(v["correct"], v["gt"]),
                          "fp_per_image": round((v["pred"] - v["matched"]) / v["images"], 2)} for k, v in groups.items()},
        "by_class": {k: {"gt": v["gt"], "matched": v["matched"], "correct": v["correct"],
                         "recall": rate(v["matched"], v["gt"]), "class_accuracy": rate(v["correct"], v["matched"])}
                     for k, v in sorted(stats.items(), key=lambda kv: -kv[1]["gt"])},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "by_source": report["by_source"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
