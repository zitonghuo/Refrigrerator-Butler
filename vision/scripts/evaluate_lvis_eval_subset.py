from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from food_recognition.open_vocab import OpenVocabularyRecognizer
from food_recognition.service import FoodRecognizer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "fruits_vegetables_lvis_eval_v1"

# Only exact semantic matches are included. Missing dataset classes count as
# unsupported coverage rather than forcing an incorrect match.
MODEL_TO_DATASET = {
    "Apple": "apple",
    "Artichoke": "artichoke",
    "Asparagus": "asparagus",
    "Banana": "banana",
    "Bell-pepper": "bell pepper/capsicum",
    "Broccoli": "broccoli",
    "Cantaloupe": "cantaloup/cantaloupe",
    "Carrot": "carrot",
    "Cucumber": "cucumber/cuke",
    "Grape": "grape",
    "Lemon": "lemon",
    "Mushroom": "mushroom",
    "Orange": "orange/orange fruit",
    "Peach": "peach",
    "Pear": "pear",
    "Pineapple": "pineapple",
    "Potato": "potato",
    "Pumpkin": "pumpkin",
    "Radish": "radish/daikon",
    "Strawberry": "strawberry",
    "Tomato": "tomato",
    "Watermelon": "watermelon",
    "Zucchini": "zucchini/courgette",
}


def parse_names(path: Path) -> dict[int, str]:
    names: dict[int, str] = {}
    in_names = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() == "names:":
            in_names = True
            continue
        if in_names:
            if ":" in line:
                key, value = line.split(":", 1)
                names[int(key.strip())] = value.strip()
    return names


def yolo_to_xyxy(values: list[float]) -> tuple[float, float, float, float]:
    x_center, y_center, width, height = values
    return (
        x_center - width / 2,
        y_center - height / 2,
        x_center + width / 2,
        y_center + height / 2,
    )


def iou(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def object_bucket(count: int) -> str:
    if count == 1:
        return "1"
    if count <= 5:
        return "2-5"
    if count <= 20:
        return "6-20"
    return "21+"


def build_world_vocabulary(
    dataset_names: list[str],
    prompt_style: str,
) -> tuple[list[str], dict[str, str]]:
    prompts: list[str] = []
    prompt_to_dataset: dict[str, str] = {}
    for dataset_name in dataset_names:
        first_name = dataset_name.split("/")[0].strip().lower()
        if prompt_style == "template":
            prompt = f"a photo of {first_name}, a food ingredient"
        else:
            prompt = first_name
        if prompt in prompt_to_dataset:
            continue
        prompts.append(prompt)
        prompt_to_dataset[prompt] = dataset_name
    return prompts, prompt_to_dataset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the current model on the local LVIS produce subset."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--weights", type=Path, default=ROOT / "weights" / "yolov8s.pt")
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--backend",
        choices=["custom", "world", "trained"],
        default="custom",
        help="custom uses the current 90-class model; world uses YOLO-World.",
    )
    parser.add_argument(
        "--world-weights",
        type=Path,
        default=ROOT / "weights" / "yolov8s-worldv2.pt",
    )
    parser.add_argument(
        "--prompt-style",
        choices=["raw", "canonical", "template"],
        default="canonical",
    )
    parser.add_argument(
        "--classifier",
        action="store_true",
        help="Reclassify detector crops with CLIP and template prompts.",
    )
    parser.add_argument("--tile-grid", type=int, default=1)
    parser.add_argument("--tile-overlap", type=float, default=0.2)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "outputs" / "lvis_eval_baseline.json",
    )
    args = parser.parse_args()

    dataset = args.dataset.resolve()
    names = parse_names(dataset / "source" / "data.yaml")
    supported_classes = (
        set(names.values())
        if args.backend in {"world", "trained"}
        else set(MODEL_TO_DATASET.values())
    )
    images = sorted((dataset / "images").glob("*.*"))
    if args.limit:
        images = images[: args.limit]

    if args.backend == "world":
        if args.prompt_style == "raw":
            world_prompts = list(names.values())
            label_map = {}
        else:
            world_prompts, label_map = build_world_vocabulary(
                list(names.values()),
                args.prompt_style,
            )
        recognizer = OpenVocabularyRecognizer(
            args.world_weights,
            prompts=world_prompts,
            label_map=label_map,
            classifier_labels=(
                list(dict.fromkeys(label_map.values())) if args.classifier else None
            ),
            device=args.device,
            confidence_threshold=args.conf,
            iou_threshold=args.iou,
            image_size=args.imgsz,
            tile_grid=args.tile_grid,
            tile_overlap=args.tile_overlap,
        )
    else:
        recognizer = FoodRecognizer(
            args.weights,
            device=args.device,
            confidence_threshold=args.conf,
            iou_threshold=args.iou,
            image_size=args.imgsz,
        )

    total_gt = 0
    total_predictions = 0
    total_matched = 0
    total_class_correct = 0
    total_false_positive = 0
    total_supported_gt = 0
    total_supported_matched = 0
    images_with_multiple = 0
    bucket_stats = defaultdict(lambda: {"images": 0, "gt": 0, "matched": 0})
    class_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {"gt": 0, "supported": 0, "matched": 0, "class_correct": 0}
    )

    for index, image_path in enumerate(images, start=1):
        label_path = dataset / "labels" / f"{image_path.stem}.txt"
        ground_truth = []
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            class_id = int(parts[0])
            ground_truth.append((names[class_id], yolo_to_xyxy(list(map(float, parts[1:])))))

        result = recognizer.predict_image(image_path)
        predictions = []
        for candidate in result.candidates:
            mapped = (
                candidate.label
                if args.backend in {"world", "trained"}
                else MODEL_TO_DATASET.get(candidate.label)
            )
            predictions.append(
                (
                    mapped,
                    candidate.bbox_xyxy[0] / result.image_width,
                    candidate.bbox_xyxy[1] / result.image_height,
                    candidate.bbox_xyxy[2] / result.image_width,
                    candidate.bbox_xyxy[3] / result.image_height,
                    candidate.confidence,
                )
            )

        image_matched = set()
        image_class_correct_indices = set()
        image_false_positive = 0
        for mapped, left, top, right, bottom, _ in sorted(
            predictions,
            key=lambda item: item[-1],
            reverse=True,
        ):
            best_index = None
            best_iou = 0.0
            for gt_index, (gt_name, gt_box) in enumerate(ground_truth):
                if gt_index in image_matched:
                    continue
                overlap = iou((left, top, right, bottom), gt_box)
                if overlap > best_iou:
                    best_iou = overlap
                    best_index = gt_index
            if best_index is None or best_iou < 0.5:
                image_false_positive += 1
                continue
            image_matched.add(best_index)
            if mapped == ground_truth[best_index][0]:
                image_class_correct_indices.add(best_index)

        if len(ground_truth) >= 2:
            images_with_multiple += 1
        bucket = object_bucket(len(ground_truth))
        bucket_stats[bucket]["images"] += 1
        bucket_stats[bucket]["gt"] += len(ground_truth)
        bucket_stats[bucket]["matched"] += len(image_matched)
        for gt_index, (gt_name, _) in enumerate(ground_truth):
            class_stats[gt_name]["gt"] += 1
            if gt_name in supported_classes:
                total_supported_gt += 1
                class_stats[gt_name]["supported"] += 1
            if gt_index in image_matched:
                class_stats[gt_name]["matched"] += 1
                if gt_name in supported_classes:
                    total_supported_matched += 1
            if gt_index in image_class_correct_indices:
                class_stats[gt_name]["class_correct"] += 1

        total_gt += len(ground_truth)
        total_predictions += len(predictions)
        total_matched += len(image_matched)
        total_class_correct += len(image_class_correct_indices)
        total_false_positive += image_false_positive

        if index % 10 == 0:
            print(f"processed {index}/{len(images)}", flush=True)

    report = {
        "settings": {
            "weights": str(recognizer.weights),
            "backend": args.backend,
            "prompt_style": args.prompt_style,
            "classifier": args.classifier,
            "tile_grid": args.tile_grid,
            "tile_overlap": args.tile_overlap,
            "device": recognizer.device,
            "confidence": args.conf,
            "iou": args.iou,
            "image_size": args.imgsz,
        },
        "summary": {
            "images": len(images),
            "images_with_multiple_objects": images_with_multiple,
            "ground_truth_objects": total_gt,
            "supported_ground_truth_objects": total_supported_gt,
            "unsupported_ground_truth_objects": total_gt - total_supported_gt,
            "predictions": total_predictions,
            "matched_objects": total_matched,
            "detection_recall": round(total_matched / total_gt, 6) if total_gt else 0,
            "supported_class_recall": (
                round(total_supported_matched / total_supported_gt, 6)
                if total_supported_gt
                else 0
            ),
            "correct_class_objects": total_class_correct,
            "class_accuracy_on_matched": (
                round(total_class_correct / total_matched, 6) if total_matched else 0
            ),
            "false_positives": total_false_positive,
            "false_positives_per_image": (
                round(total_false_positive / len(images), 6) if images else 0
            ),
        },
        "by_object_count": {
            key: {
                **value,
                "recall": round(value["matched"] / value["gt"], 6) if value["gt"] else 0,
            }
            for key, value in sorted(bucket_stats.items())
        },
        "by_ground_truth_class": dict(sorted(class_stats.items())),
        "model_class_mapping_count": (
            len(supported_classes)
        ),
        "dataset_class_count": len(names),
        "unsupported_dataset_classes": (
            []
            if args.backend in {"world", "trained"}
            else sorted(set(names.values()) - supported_classes)
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Report: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
