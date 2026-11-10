# -*- coding: utf-8 -*-
"""Fine-tune the current mseg model on v2 + DFV16 pseudo-seg data."""
from __future__ import annotations

import shutil
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(r"E:\fridge-keeper-datasets")
VISION = Path(r"E:\Refrigrerator-Butler\Refrigrerator-Butler\vision")
DATA = ROOT / "datasets" / "raw_mixed_seg_v3" / "data.yaml"
START = VISION / "weights" / "fruits_vegetables_yolov8m_seg_aicook_v1.pt"
TARGET = VISION / "weights" / "fruits_vegetables_yolov8m_seg_dfv16_v3.pt"


def main():
    model = YOLO(str(START))
    model.train(
        data=str(DATA), epochs=30, imgsz=640, batch=8, device=0,
        project=str(VISION / "runs"), name="dfv16_mixed_v3", exist_ok=True,
        workers=4, patience=15, plots=False, verbose=True,
    )
    best = VISION / "runs" / "dfv16_mixed_v3" / "weights" / "best.pt"
    if not best.exists():
        raise FileNotFoundError(best)
    shutil.copy2(best, TARGET)
    print("saved", TARGET)


if __name__ == "__main__":
    main()
