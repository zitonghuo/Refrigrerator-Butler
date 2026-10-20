from __future__ import annotations

import argparse
from pathlib import Path

import gdown


WEIGHT_URLS = {
    "yolov8s": "1f2kOOyCQ8aHzSHPH8jf9Z6cT4ai-yqmx",
    "yolov5s": "1rISMag8OCM5v99TYuavAobm3LkwjtAi9",
    "yolov5m": "1I649VGqkam_IcCCW8WUA965vPrW_pqDX",
    "yolov5l": "1sBciFcRav2ZE6jzhWnca9uegjQ4860om",
    "yolov5x": "1CRD6T9QtH9XEa-h985_Ho6jgLWu58zn0",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download upstream model weights.")
    parser.add_argument(
        "--model",
        choices=sorted(WEIGHT_URLS),
        default="yolov8s",
        help="Upstream model identifier.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("weights"),
        help="Directory for downloaded weights.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"{args.model}.pt"
    url = f"https://drive.google.com/uc?id={WEIGHT_URLS[args.model]}"
    result = gdown.download(url, str(output), quiet=False)
    if not result:
        print("Weight download failed.")
        return 1
    print(f"Saved weights to {output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
