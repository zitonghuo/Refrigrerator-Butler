from __future__ import annotations

import argparse
import base64
import json
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw


REPOSITORY = "henningheyen/Fruits-And-Vegetables-Detection-Dataset"
BRANCH = "main"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "datasets" / "fruits_vegetables_lvis_eval_v1"
API_ROOT = f"https://api.github.com/repos/{REPOSITORY}"
RAW_ROOT = f"https://raw.githubusercontent.com/{REPOSITORY}/{BRANCH}"
USER_AGENT = "FridgeKeeperDatasetBuilder/0.1"


def request_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def download(url: str, destination: Path) -> None:
    if destination.is_file() and destination.stat().st_size > 0:
        return
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=90) as response:
        destination.write_bytes(response.read())


def parse_names(data_yaml: str) -> dict[int, str]:
    names: dict[int, str] = {}
    in_names = False
    for line in data_yaml.splitlines():
        if line.strip() == "names:":
            in_names = True
            continue
        if not in_names:
            continue
        match = re.match(r"\s*(\d+):\s*(.+?)\s*$", line)
        if match:
            names[int(match.group(1))] = match.group(2)
    return names


def make_contact_sheet(
    output: Path,
    images: list[Path],
    labels: list[Path],
    names: dict[int, str],
    limit: int = 40,
) -> None:
    columns = 5
    rows = max(1, (min(limit, len(images)) + columns - 1) // columns)
    cell_width, cell_height = 320, 250
    sheet = Image.new("RGB", (columns * cell_width, rows * cell_height), "white")
    draw = ImageDraw.Draw(sheet)

    for index, (image_path, label_path) in enumerate(
        zip(images[:limit], labels[:limit])
    ):
        image = Image.open(image_path).convert("RGB")
        scale = min((cell_width - 8) / image.width, (cell_height - 28) / image.height)
        resized = image.resize(
            (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
        )
        x = (index % columns) * cell_width + 4
        y = (index // columns) * cell_height + 22
        sheet.paste(resized, (x, y))

        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            class_id, xc, yc, width, height = map(float, parts)
            left = x + int((xc - width / 2) * resized.width)
            top = y + int((yc - height / 2) * resized.height)
            right = x + int((xc + width / 2) * resized.width)
            bottom = y + int((yc + height / 2) * resized.height)
            draw.rectangle((left, top, right, bottom), outline=(220, 35, 35), width=2)
            draw.text(
                (left + 2, max(y, top - 12)),
                names.get(int(class_id), str(int(class_id))),
                fill=(180, 20, 20),
            )

        draw.text(
            (index % columns * cell_width + 6, index // columns * cell_height + 4),
            image_path.name[:38],
            fill=(30, 30, 30),
        )

    sheet.save(output, quality=88)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a local evaluation subset from the MIT-licensed LVIS produce dataset."
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of test images. 0 means all 180 images.",
    )
    args = parser.parse_args()

    output = args.output.resolve()
    images_dir = output / "images"
    labels_dir = output / "labels"
    source_dir = output / "source"
    for folder in (images_dir, labels_dir, source_dir):
        folder.mkdir(parents=True, exist_ok=True)

    tree = request_json(
        f"{API_ROOT}/git/trees/{BRANCH}?recursive=1"
    )
    blobs = [item for item in tree["tree"] if item["type"] == "blob"]
    image_paths = sorted(
        item["path"]
        for item in blobs
        if item["path"].startswith("LVIS_Fruits_And_Vegetables/images/test/")
        and item["path"].lower().endswith((".jpg", ".jpeg", ".png"))
    )
    if args.limit > 0:
        image_paths = image_paths[: args.limit]
    if not image_paths:
        raise RuntimeError("No test images were found in the upstream repository.")

    label_paths = [
        path.replace("/images/test/", "/labels/test/").rsplit(".", 1)[0] + ".txt"
        for path in image_paths
    ]

    for relative_path in [*image_paths, *label_paths]:
        destination = output / Path(relative_path).relative_to(
            "LVIS_Fruits_And_Vegetables"
        )
        if "labels" in destination.parts:
            destination = labels_dir / destination.name
        else:
            destination = images_dir / destination.name
        download(f"{RAW_ROOT}/{quote(relative_path)}", destination)

    data_yaml = request_json(
        f"{API_ROOT}/contents/LVIS_Fruits_And_Vegetables/data.yaml?ref={BRANCH}"
    )
    data_yaml_text = base64.b64decode(data_yaml["content"]).decode("utf-8")
    (source_dir / "data.yaml").write_text(data_yaml_text, encoding="utf-8")
    names = parse_names(data_yaml_text)

    for path in ("LICENSE", "fruits_vegetables_LVIS_dict.json"):
        download(f"{RAW_ROOT}/{quote(path)}", source_dir / Path(path).name)

    local_images = [images_dir / Path(path).name for path in image_paths]
    local_labels = [labels_dir / Path(path).name for path in label_paths]
    class_counts: Counter[str] = Counter()
    image_box_counts: list[int] = []
    manifest = []

    for image_path, label_path in zip(local_images, local_labels):
        labels = []
        for line in label_path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if len(parts) != 5:
                continue
            class_name = names.get(int(parts[0]), str(parts[0]))
            labels.append(class_name)
            class_counts[class_name] += 1
        image_box_counts.append(len(labels))
        manifest.append(
            {
                "image": f"images/{image_path.name}",
                "label": f"labels/{label_path.name}",
                "source_image_url": (
                    f"https://github.com/{REPOSITORY}/blob/{BRANCH}/"
                    f"LVIS_Fruits_And_Vegetables/images/test/{quote(image_path.name)}"
                ),
                "source_label_url": (
                    f"https://github.com/{REPOSITORY}/blob/{BRANCH}/"
                    f"LVIS_Fruits_And_Vegetables/labels/test/{quote(label_path.name)}"
                ),
                "objects": labels,
            }
        )

    (output / "manifest.jsonl").write_text(
        "\n".join(json.dumps(item, ensure_ascii=False) for item in manifest) + "\n",
        encoding="utf-8",
    )
    statistics = {
        "source_repository": f"https://github.com/{REPOSITORY}",
        "source_license": "MIT repository license; LVIS source image licenses may differ",
        "image_count": len(local_images),
        "object_count": sum(image_box_counts),
        "images_with_multiple_objects": sum(count >= 2 for count in image_box_counts),
        "max_objects_in_one_image": max(image_box_counts, default=0),
        "class_count": len(class_counts),
        "class_counts": dict(class_counts.most_common()),
    }
    (output / "statistics.json").write_text(
        json.dumps(statistics, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    make_contact_sheet(
        output / "contact_sheet.jpg",
        local_images,
        local_labels,
        names,
    )
    print(json.dumps(statistics, ensure_ascii=False, indent=2))
    print(f"Dataset: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
