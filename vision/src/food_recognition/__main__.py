from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .service import DEFAULT_WEIGHTS, FoodRecognizer


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the Fridge Butler image food recognizer."
    )
    parser.add_argument(
        "--image",
        required=True,
        type=Path,
        help="Image path to analyze.",
    )
    parser.add_argument(
        "--weights",
        type=Path,
        default=DEFAULT_WEIGHTS,
        help="YOLO weights path. Default: weights/yolov8s.pt",
    )
    parser.add_argument(
        "--device",
        default="auto",
        help="Inference device: auto, cpu, 0, 1, ...",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.25,
        help="Minimum confidence.",
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.5,
        help="NMS IoU threshold.",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="Inference image size.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON output path.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        recognizer = FoodRecognizer(
            args.weights,
            device=args.device,
            confidence_threshold=args.conf,
            iou_threshold=args.iou,
            image_size=args.imgsz,
        )
        result = recognizer.predict_image(args.image)
        output = result.to_json()
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"food-recognition: {error}", file=sys.stderr)
        return 1

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
