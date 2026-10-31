# -*- coding: utf-8 -*-
"""Evaluate a trained unified detector on the held-out merged split."""
from __future__ import annotations

import argparse
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path

from food_recognition.service import FoodRecognizer


def parse_names(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    in_names = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "names:":
            in_names = True
            continue
        if in_names and ":" in line:
            key, value = line.split(":", 1)
            names[int(key.strip())] = value.strip()
    return names


def yolo_to_xyxy(values):
    cx, cy, w, h = values
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def iou(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    overlap = max(0.0, right - left) * max(0.0, bottom - top)
    area_a = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    area_b = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    union = area_a + area_b - overlap
    return overlap / union if union else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\china_fridge_v1"))
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--split", default="val")
    parser.add_argument("--output", type=Path, default=Path("outputs/china_fridge_v1_eval.json"))
    args = parser.parse_args()

    names = parse_names(args.dataset / "data.yaml")
    recognizer = FoodRecognizer(args.weights, device=args.device, confidence_threshold=args.conf, image_size=args.imgsz)
    stats = defaultdict(lambda: {"gt": 0, "matched": 0, "correct": 0})
    groups = defaultdict(lambda: {"images": 0, "gt": 0, "matched": 0, "correct": 0, "fp": 0})
    errors = []
    images = sorted((args.dataset / "images" / args.split).glob("*.*"))

    for image in images:
        label = args.dataset / "labels" / args.split / (image.stem + ".txt")
        gt = []
        if label.exists():
            for line in label.read_text(encoding="utf-8").splitlines():
                parts = line.split()
                if len(parts) == 5:
                    gt.append((names[int(parts[0])], yolo_to_xyxy(list(map(float, parts[1:])))))
        result = recognizer.predict_image(image)
        preds = [
            (c.label, c.bbox_xyxy[0] / result.image_width, c.bbox_xyxy[1] / result.image_height,
             c.bbox_xyxy[2] / result.image_width, c.bbox_xyxy[3] / result.image_height, c.confidence)
            for c in result.candidates
        ]
        matched = set()
        correct = set()
        fp = 0
        for label_name, left, top, right, bottom, _ in sorted(preds, key=lambda x: x[-1], reverse=True):
            best_i, best = None, 0.0
            for i, (_, box) in enumerate(gt):
                if i in matched:
                    continue
                overlap = iou((left, top, right, bottom), box)
                if overlap > best:
                    best, best_i = overlap, i
            if best_i is None or best < 0.5:
                fp += 1
                continue
            matched.add(best_i)
            if label_name == gt[best_i][0]:
                correct.add(best_i)
        for i, (name, _) in enumerate(gt):
            stats[name]["gt"] += 1
            if i in matched:
                stats[name]["matched"] += 1
            if i in correct:
                stats[name]["correct"] += 1
        source = "foodinsseg" if image.name.startswith("fis_") else "lvis"
        g = groups[source]
        g["images"] += 1
        g["gt"] += len(gt)
        g["matched"] += len(matched)
        g["correct"] += len(correct)
        g["fp"] += fp
        errors.append(len(preds) - len(gt))

    def ratio(a, b):
        return round(a / b, 4) if b else None

    total_gt = sum(v["gt"] for v in stats.values())
    total_matched = sum(v["matched"] for v in stats.values())
    total_correct = sum(v["correct"] for v in stats.values())
    report = {
        "settings": {"weights": str(args.weights), "conf": args.conf, "imgsz": args.imgsz},
        "overall": {
            "images": len(images), "gt": total_gt, "matched": total_matched,
            "correct": total_correct,
            "recall": ratio(total_matched, total_gt),
            "class_accuracy": ratio(total_correct, total_matched),
            "end_to_end": ratio(total_correct, total_gt),
            "fp_per_image": round(sum(g["fp"] for g in groups.values()) / len(images), 2),
            "exact_count_rate": ratio(sum(1 for e in errors if e == 0), len(images)),
            "mean_count_error": round(statistics.mean(errors), 2),
        },
        "by_source": {
            k: {"images": v["images"], "gt": v["gt"], "matched": v["matched"], "correct": v["correct"],
                "recall": ratio(v["matched"], v["gt"]), "class_accuracy": ratio(v["correct"], v["matched"]),
                "end_to_end": ratio(v["correct"], v["gt"]), "fp_per_image": round(v["fp"] / v["images"], 2)}
            for k, v in groups.items()
        },
        "by_class": {
            k: {"gt": v["gt"], "matched": v["matched"], "correct": v["correct"],
                "recall": ratio(v["matched"], v["gt"]), "class_accuracy": ratio(v["correct"], v["matched"])}
            for k, v in sorted(stats.items(), key=lambda kv: -kv[1]["gt"])
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "by_source": report["by_source"]}, ensure_ascii=False, indent=2))
    print("written", args.output)


if __name__ == "__main__":
    main()
