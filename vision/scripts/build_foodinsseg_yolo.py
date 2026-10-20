from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "FoodInsSeg"

# Only ingredients normally stored in a refrigerator or freezer are retained.
CATEGORY_MAP = {
    "apple": "apple",
    "avocado": "avocado",
    "banana": "banana",
    "blueberry": "blueberry",
    "cherry": "cherry",
    "grape": "grape",
    "kiwi": "kiwi",
    "lemon": "lemon",
    "mango": "mango",
    "melon": "melon",
    "orange": "orange",
    "peach": "peach",
    "pear": "pear",
    "pineapple": "pineapple",
    "strawberry": "strawberry",
    "watermelon": "watermelon",
    "asparagus": "asparagus",
    "bean sprouts": "bean_sprout",
    "broccoli": "broccoli",
    "cabbage": "cabbage",
    "carrot": "carrot",
    "cauliflower": "cauliflower",
    "celery stick": "celery",
    "corn": "corn",
    "cucumber": "cucumber",
    "eggplant": "eggplant",
    "enoki mushroom": "enoki_mushroom",
    "french beans": "green_bean",
    "green beans": "green_bean",
    "kelp": "kelp",
    "king oyster mushroom": "mushroom",
    "lettuce": "lettuce",
    "okra": "okra",
    "oyster mushroom": "mushroom",
    "pepper": "bell_pepper",
    "pumpkin": "pumpkin",
    "rape": "bok_choy",
    "seaweed": "kelp",
    "shiitake": "shiitake",
    "spring onion": "scallion",
    "tomato": "tomato",
    "white button mushroom": "mushroom",
    "white radish": "radish",
    "cheese butter": "cheese",
    "egg": "egg",
    "milk": "milk",
    "chicken duck": "chicken",
    "crab": "crab",
    "fish": "fish",
    "fried meat": "cooked_meat",
    "lamb": "lamb",
    "pork": "pork",
    "shellfish": "shellfish",
    "shrimp": "shrimp",
    "steak": "beef",
    "hanamaki baozi": "steamed_bun",
    "noodles": "fresh_noodles",
    "rice": "leftover_rice",
    "soup": "soup",
    "tofu": "tofu",
    "wonton dumplings": "dumpling",
}


def convert_split(
    annotation_path: Path,
    label_dir: Path,
    class_to_id: dict[str, int],
) -> Counter:
    data = json.loads(annotation_path.read_text(encoding="utf-8"))
    categories = {item["id"]: item["name"] for item in data["categories"]}
    images = {item["id"]: item for item in data["images"]}
    grouped: dict[int, list[str]] = {}
    counts: Counter = Counter()

    for annotation in data["annotations"]:
        category_name = categories[annotation["category_id"]].strip().casefold()
        target_name = CATEGORY_MAP.get(category_name)
        if target_name is None:
            continue
        image = images[annotation["image_id"]]
        left, top, width, height = annotation["bbox"]
        image_width = float(image["width"])
        image_height = float(image["height"])
        x_center = (left + width / 2) / image_width
        y_center = (top + height / 2) / image_height
        normalized_width = width / image_width
        normalized_height = height / image_height
        if normalized_width <= 0 or normalized_height <= 0:
            continue
        line = " ".join(
            [
                str(class_to_id[target_name]),
                f"{x_center:.6f}",
                f"{y_center:.6f}",
                f"{normalized_width:.6f}",
                f"{normalized_height:.6f}",
            ]
        )
        grouped.setdefault(annotation["image_id"], []).append(line)
        counts[target_name] += 1

    label_dir.mkdir(parents=True, exist_ok=True)
    for image_id, lines in grouped.items():
        label_path = label_dir / f"{Path(images[image_id]['file_name']).stem}.txt"
        label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert FoodInsSeg COCO annotations to a filtered YOLO dataset."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    dataset = args.dataset.resolve()
    annotations = dataset / "annotations"
    if not (annotations / "Train.json").is_file():
        raise FileNotFoundError("FoodInsSeg annotations are missing.")

    class_names = sorted(set(CATEGORY_MAP.values()))
    class_to_id = {name: index for index, name in enumerate(class_names)}
    counts = Counter()
    counts.update(
        convert_split(
            annotations / "Train.json",
            dataset / "labels" / "train",
            class_to_id,
        )
    )
    counts.update(
        convert_split(
            annotations / "Test.json",
            dataset / "labels" / "test",
            class_to_id,
        )
    )

    data_yaml = {
        "path": str(dataset),
        "train": "images/train",
        "val": "images/test",
        "test": "images/test",
        "names": {index: name for index, name in enumerate(class_names)},
    }
    yaml_path = dataset / "fridge_ingredients_data.yaml"
    yaml_path.write_text(
        yaml.safe_dump(data_yaml, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    stats = {
        "classes": len(class_names),
        "instances": sum(counts.values()),
        "class_counts": dict(counts.most_common()),
    }
    (dataset / "fridge_ingredients_stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"YOLO data: {yaml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
