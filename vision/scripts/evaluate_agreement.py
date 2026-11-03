# -*- coding: utf-8 -*-
"""Evaluate detector/classifier agreement as an auto-submit gate."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import torch
import yaml
from PIL import Image, ImageOps
from torchvision import models, transforms

from food_recognition.service import FoodRecognizer

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)
CLASS_MAP = {
    "apple": "apple", "apricot": "apricot", "avocado": "avocado",
    "banana": "banana", "bell_pepper": "bell pepper/capsicum",
    "blueberry": "blueberry", "cantaloup": "cantaloup/cantaloupe",
    "cauliflower": "cauliflower", "cherry": "cherry",
    "cucumber": "cucumber/cuke", "date": "date/date fruit",
    "edible_corn": "edible corn/corn/maize", "eggplant": "eggplant/aubergine",
    "ginger": "ginger/gingerroot", "grape": "grape",
    "kiwi_fruit": "kiwi fruit", "lemon": "lemon",
    "mandarin_orange": "mandarin orange", "melon": "melon",
    "onion": "onion", "orange": "orange/orange fruit", "papaya": "papaya",
    "peach": "peach", "pear": "pear", "persimmon": "persimmon",
    "pineapple": "pineapple", "potato": "potato", "strawberry": "strawberry",
    "tomato": "tomato", "watermelon": "watermelon",
}


def iou(a, b):
    left, top = max(a[0], b[0]), max(a[1], b[1])
    right, bottom = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, right - left) * max(0.0, bottom - top)
    aa = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    bb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (aa + bb - inter) if aa + bb - inter else 0.0


def xyxy(v):
    cx, cy, w, h = v
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--detector", type=Path, required=True)
    parser.add_argument("--classifier", type=Path, required=True)
    parser.add_argument("--split", default="test")
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--cls-threshold", type=float, default=0.5)
    parser.add_argument("--device", default="0")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() and args.device != "cpu" else "cpu")
    ckpt = torch.load(args.classifier, map_location=device)
    classes = ckpt["classes"]
    model = models.resnet18(weights=None)
    model.fc = torch.nn.Linear(model.fc.in_features, len(classes))
    model.load_state_dict(ckpt["state_dict"])
    model.to(device).eval()
    tf = transforms.Compose([transforms.Resize(256), transforms.CenterCrop(224),
                             transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    recognizer = FoodRecognizer(args.detector, device=args.device, confidence_threshold=args.conf, image_size=640)
    names = {int(k): v for k, v in yaml.safe_load((args.dataset / "data.yaml").read_text(encoding="utf-8"))["names"].items()}

    counts = defaultdict(int)
    for image_path in sorted((args.dataset / "images" / args.split).glob("*.*")):
        label_path = args.dataset / "labels" / args.split / (image_path.stem + ".txt")
        gt = []
        if label_path.exists():
            for line in label_path.read_text(encoding="utf-8").splitlines():
                p = line.split()
                if len(p) == 5:
                    gt.append((names[int(p[0])], xyxy(list(map(float, p[1:])))))
        counts["gt"] += len(gt)
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            width, height = im.size
            result = recognizer.predict_image(image_path)
            crops, candidates = [], []
            for candidate in result.candidates:
                x1, y1, x2, y2 = candidate.bbox_xyxy
                pad_x, pad_y = (x2 - x1) * 0.1, (y2 - y1) * 0.1
                box = (max(0, int(x1 - pad_x)), max(0, int(y1 - pad_y)),
                       min(width, int(x2 + pad_x)), min(height, int(y2 + pad_y)))
                crops.append(tf(ImageOps.pad(im.crop(box), (224, 224), color=(127, 127, 127))))
                candidates.append(candidate)
            if not crops:
                continue
            with torch.no_grad():
                probs = torch.softmax(model(torch.stack(crops).to(device)), dim=1)
            top_probs, top_idx = probs.max(dim=1)

            matched = set()
            for i, candidate in enumerate(candidates):
                box = [candidate.bbox_xyxy[0] / width, candidate.bbox_xyxy[1] / height,
                       candidate.bbox_xyxy[2] / width, candidate.bbox_xyxy[3] / height]
                best_i, best = None, 0.0
                for j, (_, gt_box) in enumerate(gt):
                    if j in matched:
                        continue
                    overlap = iou(box, gt_box)
                    if overlap > best:
                        best, best_i = overlap, j
                is_matched = best_i is not None and best >= 0.5
                if is_matched:
                    matched.add(best_i)
                detector_correct = is_matched and candidate.label == gt[best_i][0]
                classifier_label = CLASS_MAP.get(classes[int(top_idx[i])])
                classifier_correct = is_matched and classifier_label == gt[best_i][0]
                counts["detections"] += 1
                counts["matched"] += int(is_matched)
                counts["detector_correct"] += int(detector_correct)
                if classifier_label is None or float(top_probs[i]) < args.cls_threshold:
                    counts["no_classifier"] += 1
                    continue
                if classifier_label == candidate.label:
                    counts["agreed"] += 1
                    counts["agreed_matched"] += int(is_matched)
                    counts["agreed_correct"] += int(detector_correct)
                else:
                    counts["disagreed"] += 1
                    counts["disagreed_matched"] += int(is_matched)
                    counts["detector_right_disagreed"] += int(detector_correct)
                    counts["classifier_right_disagreed"] += int(classifier_correct)
                    counts["either_right_disagreed"] += int(detector_correct or classifier_correct)

    result = {
        "settings": {"conf": args.conf, "cls_threshold": args.cls_threshold},
        "counts": dict(counts),
        "auto_agreement": {
            "auto_submitted": counts["agreed"],
            "precision": round(counts["agreed_correct"] / counts["agreed"], 4) if counts["agreed"] else None,
            "recall_of_gt": round(counts["agreed_correct"] / counts["gt"], 4) if counts["gt"] else None,
            "auto_submit_rate": round(counts["agreed"] / counts["detections"], 4) if counts["detections"] else None,
        },
        "disagreement": {
            "count": counts["disagreed"],
            "detector_right": counts["detector_right_disagreed"],
            "classifier_right": counts["classifier_right_disagreed"],
            "either_right": counts["either_right_disagreed"],
            "user_choice_upper_bound": round(counts["either_right_disagreed"] / counts["disagreed_matched"], 4) if counts["disagreed_matched"] else None,
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
