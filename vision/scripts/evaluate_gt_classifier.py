from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from PIL import Image

from food_recognition.open_vocab import OpenVocabularyRecognizer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "fruits_vegetables_lvis_eval_v1"


def parse_names(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    in_names = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "names:":
            in_names = True
        elif in_names and ":" in line:
            key, value = line.split(":", 1)
            names[int(key.strip())] = value.strip()
    return names


def canonical_dataset_labels(dataset_names: list[str]) -> tuple[list[str], list[str]]:
    grouped: dict[str, list[str]] = {}
    for name in dataset_names:
        canonical = name.split("/")[0].strip().lower()
        grouped.setdefault(canonical, []).append(name)
    canonical_names = list(grouped)
    original_names = [
        next((name for name in grouped[canonical] if name.islower()), grouped[canonical][0])
        for canonical in canonical_names
    ]
    return canonical_names, original_names


def yolo_to_xyxy(values: list[float]) -> list[int]:
    x_center, y_center, width, height = values
    return [
        int((x_center - width / 2) * 10000),
        int((y_center - height / 2) * 10000),
        int((x_center + width / 2) * 10000),
        int((y_center + height / 2) * 10000),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Measure CLIP top-1 and top-5 accuracy on ground-truth crops."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "gt_classifier_accuracy.json",
    )
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    names = parse_names(dataset / "source" / "data.yaml")
    canonical_prompts, classifier_labels = canonical_dataset_labels(list(names.values()))
    recognizer = OpenVocabularyRecognizer(
        ROOT / "weights" / "yolov8s-worldv2.pt",
        prompts=canonical_prompts,
        classifier_labels=classifier_labels,
        device=args.device,
    )
    if recognizer.clip_model is None or recognizer.clip_text_features is None:
        raise RuntimeError("CLIP classifier failed to initialize.")

    images = sorted((dataset / "images").glob("*.*"))
    if args.limit:
        images = images[: args.limit]
    correct_top1 = 0
    correct_top5 = 0
    total = 0
    per_class = {
        label: {"total": 0, "top1": 0, "top5": 0}
        for label in classifier_labels
    }

    for image_index, image_path in enumerate(images, start=1):
        label_path = dataset / "labels" / f"{image_path.stem}.txt"
        rows = []
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) == 5:
                rows.append((names[int(parts[0])], list(map(float, parts[1:]))))
        if not rows:
            continue

        with Image.open(image_path) as source:
            image = source.convert("RGB")
            boxes = []
            for _, values in rows:
                left, top, right, bottom = yolo_to_xyxy(values)
                boxes.append(
                    [
                        int(left * image.width / 10000),
                        int(top * image.height / 10000),
                        int(right * image.width / 10000),
                        int(bottom * image.height / 10000),
                    ]
                )
            crops = []
            for left, top, right, bottom in boxes:
                left = max(0, min(left, image.width - 1))
                top = max(0, min(top, image.height - 1))
                right = max(left + 1, min(right, image.width))
                bottom = max(top + 1, min(bottom, image.height))
                crops.append(recognizer.clip_preprocess(image.crop((left, top, right, bottom))))

            with torch.no_grad():
                for start in range(0, len(crops), 64):
                    batch = torch.stack(crops[start : start + 64]).to(
                        recognizer.torch_device
                    )
                    features = recognizer.clip_model.encode_image(batch)
                    features = features / features.norm(dim=-1, keepdim=True)
                    probabilities = (
                        100.0 * features @ recognizer.clip_text_features.T
                    ).softmax(dim=-1)
                    values, indices = probabilities.topk(5, dim=-1)
                    for row_index, (gt_name, _) in enumerate(
                        rows[start : start + 64],
                        start=start,
                    ):
                        candidates = [
                            classifier_labels[int(index.item())]
                            for index in indices[row_index - start]
                        ]
                        total += 1
                        per_class[gt_name]["total"] += 1
                        if candidates[0] == gt_name:
                            correct_top1 += 1
                            per_class[gt_name]["top1"] += 1
                        if gt_name in candidates:
                            correct_top5 += 1
                            per_class[gt_name]["top5"] += 1
        if image_index % 20 == 0:
            print(f"processed {image_index}/{len(images)}", flush=True)

    report = {
        "images": len(images),
        "crops": total,
        "top1_accuracy": round(correct_top1 / total, 6) if total else 0,
        "top5_accuracy": round(correct_top5 / total, 6) if total else 0,
        "per_class": per_class,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: report[key] for key in ("images", "crops", "top1_accuracy", "top5_accuracy")}, indent=2))
    print(f"Report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
