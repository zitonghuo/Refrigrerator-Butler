# -*- coding: utf-8 -*-
"""Evaluate the produce detector with occlusion / density / class breakdowns."""
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


def area(box):
    return max(0.0, box[2] - box[0]) * max(0.0, box[3] - box[1])


def inter(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    return max(0.0, right - left) * max(0.0, bottom - top)


def iou(a, b):
    overlap = inter(a, b)
    union = area(a) + area(b) - overlap
    return overlap / union if union else 0.0


def occluded_fraction(index, boxes):
    own = boxes[index]
    own_area = area(own)
    if own_area <= 0:
        return 0.0
    # fraction of this box covered by the most overlapping neighbour
    return max((inter(own, other) / own_area for j, other in enumerate(boxes) if j != index), default=0.0)


def bucket(count):
    if count == 0:
        return "0"
    if count == 1:
        return "1"
    if count <= 5:
        return "2-5"
    if count <= 20:
        return "6-20"
    return "21+"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path(r"E:\fridge-keeper-datasets\datasets\fruits_vegetables_lvis_eval_v1"))
    parser.add_argument("--weights", type=Path, default=Path("weights/fruits_vegetables_yolov8s_v1.pt"))
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    parser.add_argument("--output", type=Path, default=Path("outputs/occlusion_eval.json"))
    args = parser.parse_args()

    dataset = args.dataset.resolve()
    names = parse_names(dataset / "source" / "data.yaml")
    recognizer = FoodRecognizer(
        args.weights,
        device=args.device,
        confidence_threshold=args.conf,
        iou_threshold=0.5,
        image_size=args.imgsz,
    )

    per_image = []
    class_stats = defaultdict(lambda: {"gt": 0, "matched": 0, "correct": 0})
    occlusion_stats = defaultdict(lambda: {"gt": 0, "matched": 0, "correct": 0})
    bucket_stats = defaultdict(lambda: {"images": 0, "gt": 0, "matched": 0, "correct": 0})
    confusion = Counter()
    count_errors = []

    for manifest_line in (dataset / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if not manifest_line.strip():
            continue
        item = json.loads(manifest_line)
        image_path = dataset / item["image"]
        label_path = dataset / item["label"]
        gt = []
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            gt.append((names[int(parts[0])], yolo_to_xyxy(list(map(float, parts[1:])))))

        boxes = [box for _, box in gt]
        occlusions = [occluded_fraction(i, boxes) for i in range(len(gt))]
        result = recognizer.predict_image(image_path)
        preds = [
            (c.label, c.bbox_xyxy[0] / result.image_width, c.bbox_xyxy[1] / result.image_height,
             c.bbox_xyxy[2] / result.image_width, c.bbox_xyxy[3] / result.image_height, c.confidence)
            for c in result.candidates
        ]

        matched_gt = set()
        correct_gt = set()
        fp = 0
        for label, left, top, right, bottom, _ in sorted(preds, key=lambda x: x[-1], reverse=True):
            best_i, best = None, 0.0
            for i, (_, box) in enumerate(gt):
                if i in matched_gt:
                    continue
                overlap = iou((left, top, right, bottom), box)
                if overlap > best:
                    best, best_i = overlap, i
            if best_i is None or best < 0.5:
                fp += 1
                continue
            matched_gt.add(best_i)
            if label == gt[best_i][0]:
                correct_gt.add(best_i)
            else:
                confusion[(gt[best_i][0], label)] += 1

        for i, (name, _) in enumerate(gt):
            cls = class_stats[name]
            cls["gt"] += 1
            occl = occlusions[i]
            level = "none" if occl < 0.1 else "partial" if occl < 0.4 else "heavy"
            occ = occlusion_stats[level]
            occ["gt"] += 1
            if i in matched_gt:
                cls["matched"] += 1
                occ["matched"] += 1
                if i in correct_gt:
                    cls["correct"] += 1
                    occ["correct"] += 1

        b = bucket(len(gt))
        bucket_stats[b]["images"] += 1
        bucket_stats[b]["gt"] += len(gt)
        bucket_stats[b]["matched"] += len(matched_gt)
        bucket_stats[b]["correct"] += len(correct_gt)
        count_errors.append(len(preds) - len(gt))
        per_image.append({
            "image": item["image"], "gt": len(gt), "pred": len(preds),
            "matched": len(matched_gt), "correct": len(correct_gt), "fp": fp,
            "heavy_occlusion_objects": sum(1 for x in occlusions if x >= 0.4),
        })

    total_gt = sum(x["gt"] for x in per_image)
    total_matched = sum(x["matched"] for x in per_image)
    total_correct = sum(x["correct"] for x in per_image)
    total_pred = sum(x["pred"] for x in per_image)
    image_count = len(per_image)

    def ratio(a, b):
        return round(a / b, 4) if b else None

    report = {
        "settings": {"weights": str(args.weights), "conf": args.conf, "imgsz": args.imgsz, "device": args.device},
        "overall": {
            "images": image_count,
            "ground_truth_objects": total_gt,
            "predictions": total_pred,
            "matched_objects": total_matched,
            "correct_class_objects": total_correct,
            "detection_recall": ratio(total_matched, total_gt),
            "class_accuracy_on_matched": ratio(total_correct, total_matched),
            "false_positives_per_image": round((total_pred - total_matched) / image_count, 2),
        },
        "by_object_count": {
            k: {"images": v["images"], "gt": v["gt"], "matched": v["matched"],
                "recall": ratio(v["matched"], v["gt"]),
                "class_accuracy": ratio(v["correct"], v["matched"])}
            for k, v in sorted(bucket_stats.items())
        },
        "by_occlusion": {
            k: {"gt": v["gt"], "matched": v["matched"], "correct": v["correct"],
                "recall": ratio(v["matched"], v["gt"]),
                "class_accuracy": ratio(v["correct"], v["matched"])}
            for k, v in sorted(occlusion_stats.items())
        },
        "by_class": {
            k: {"gt": v["gt"], "matched": v["matched"], "correct": v["correct"],
                "recall": ratio(v["matched"], v["gt"]),
                "class_accuracy": ratio(v["correct"], v["matched"])}
            for k, v in sorted(class_stats.items(), key=lambda kv: -kv[1]["gt"])
        },
        "top_confusions": [
            {"true": a, "predicted": b, "count": c}
            for (a, b), c in confusion.most_common(15)
        ],
        "quantity": {
            "exact_count_match_images": sum(1 for x in per_image if x["pred"] == x["gt"]),
            "exact_count_match_rate": ratio(sum(1 for x in per_image if x["pred"] == x["gt"]), image_count),
            "mean_signed_error": round(statistics.mean(count_errors), 2),
            "median_absolute_error": statistics.median(abs(x) for x in count_errors),
        },
        "images": per_image,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("overall", "by_object_count", "by_occlusion", "quantity")}, ensure_ascii=False, indent=2))
    print("written", args.output)


if __name__ == "__main__":
    main()
