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
    parser.add_argument("--lr0", type=float, default=0.01)
    parser.add_argument("--freeze", type=int, default=0)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--mixup", type=float, default=0.0)
    parser.add_argument("--scale", type=float, default=0.5)
    parser.add_argument("--style-augment", action="store_true")
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
        patience=args.patience,
        cache=False,
        amp=args.amp,
        lr0=args.lr0,
        freeze=args.freeze,
        mixup=(0.2 if args.style_augment else args.mixup),
        scale=(0.7 if args.style_augment else args.scale),
        **(dict(
            hsv_h=0.03, hsv_s=0.9, hsv_v=0.6,
            degrees=15, translate=0.2, shear=3,
            perspective=0.001, flipud=0.1, fliplr=0.5,
            mosaic=1.0, erasing=0.4, close_mosaic=10,
        ) if args.style_augment else {}),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
