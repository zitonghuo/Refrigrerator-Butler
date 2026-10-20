from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a produce detector.")
    parser.add_argument(
        "--model",
        type=Path,
        default=ROOT / "weights" / "yolov8s.pt",
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=ROOT
        / "datasets"
        / "fruits_vegetables_lvis_full"
        / "data.yaml",
    )
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--amp", action="store_true")
    parser.add_argument("--name", default="lvis_produce_v1")
    args = parser.parse_args()

    model = YOLO(str(args.model))
    model.train(
        data=str(args.data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        project=str((ROOT / "runs").resolve()),
        name=args.name,
        exist_ok=True,
        plots=False,
        patience=5,
        cache=False,
        amp=args.amp,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
