# -*- coding: utf-8 -*-
"""Generate YOLO-seg labels from DFV16 boxes with SAM box prompts."""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image, ImageDraw
from segment_anything import SamPredictor, sam_model_registry

ROOT = Path(r"E:\fridge-keeper-datasets")
SRC = ROOT / "datasets" / "dfv16_v1"
OUT = ROOT / "datasets" / "dfv16_seg_v1"
CKPT = ROOT / "sam_vit_b_01ec64.pth"
SPLITS = ("train", "val")
MAP = {0: 1, 1: 1, 2: 4, 3: 5, 4: 16, 5: 17, 6: 19, 7: 25, 8: 26, 10: 32, 11: 36, 12: 7, 14: 39, 15: 44}


def largest_polygon(mask, w, h):
    m = (mask.astype(np.uint8) > 0).astype(np.uint8)
    contours, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    c = max(contours, key=cv2.contourArea)
    if cv2.contourArea(c) < 100:
        return None
    eps = 0.004 * cv2.arcLength(c, True)
    c = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
    if len(c) < 3:
        return None
    return [[float(x) / w, float(y) / h] for x, y in c]


def main():
    for split in SPLITS:
        for sub in ("images", "labels"):
            (OUT / split / sub).mkdir(parents=True, exist_ok=True)
    (OUT / "audit").mkdir(parents=True, exist_ok=True)
    sam = sam_model_registry["vit_b"](checkpoint=str(CKPT)).cuda().eval()
    predictor = SamPredictor(sam)
    stats = {"images": 0, "objects": 0, "accepted": 0, "rejected": 0, "no_poly": 0, "score_reject": 0, "area_reject": 0, "audit": []}
    started = time.time()
    for split in SPLITS:
        for img_path in sorted((SRC / split / "images").glob("*.jpg")):
            label_path = SRC / split / "labels" / (img_path.stem + ".txt")
            if not label_path.exists():
                continue
            lines = [x for x in label_path.read_text().splitlines() if x.strip()]
            objects = []
            for line in lines:
                p = line.split()
                cid = int(p[0])
                if cid not in MAP:
                    continue
                cx, cy, bw, bh = map(float, p[1:5])
                objects.append((MAP[cid], np.array([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], dtype=np.float32)))
            if not objects:
                continue
            img = Image.open(img_path).convert("RGB")
            w, h = img.size
            predictor.set_image(np.array(img))
            seg_labels = []
            overlay = img.convert('RGBA')
            draw = ImageDraw.Draw(overlay)
            for cls, box in objects:
                stats["objects"] += 1
                x1, y1, x2, y2 = [float(v) * (w if i % 2 == 0 else h) for i, v in enumerate(box)]
                masks, scores, _ = predictor.predict(box=np.array([x1, y1, x2, y2]), multimask_output=True)
                best = int(np.argmax(scores))
                mask = masks[best].astype(np.uint8)
                score = float(scores[best])
                box_area = max((x2 - x1) * (y2 - y1), 1)
                area_ratio = float(mask.sum()) / box_area
                if score < 0.80:
                    stats["score_reject"] += 1
                    stats["rejected"] += 1
                    continue
                if not (0.25 <= area_ratio <= 1.2):
                    stats["area_reject"] += 1
                    stats["rejected"] += 1
                    continue
                ys, xs = np.where(mask > 0)
                if len(xs) == 0:
                    stats["area_reject"] += 1
                    stats["rejected"] += 1
                    continue
                mb = [xs.min(), ys.min(), xs.max(), ys.max()]
                ix1, iy1 = max(x1, mb[0]), max(y1, mb[1])
                ix2, iy2 = min(x2, mb[2]), min(y2, mb[3])
                inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
                union = max((x2 - x1) * (y2 - y1), 1) + max((mb[2] - mb[0]) * (mb[3] - mb[1]), 1) - inter
                if inter / union < 0.65:
                    stats["bbox_reject"] = stats.get("bbox_reject", 0) + 1
                    stats["rejected"] += 1
                    continue
                poly = largest_polygon(mask, w, h)
                if poly is None:
                    stats["no_poly"] += 1
                    stats["rejected"] += 1
                    continue
                seg_labels.append((cls, poly))
                stats["accepted"] += 1
                mm = Image.fromarray(mask * 255).resize((w, h), Image.Resampling.NEAREST)
                color = (255, 80, 80) if cls in (1, 5, 32) else (80, 180, 255)
                overlay = Image.composite(Image.new('RGBA', (w, h), color + (90,)), overlay, mm)
                draw = ImageDraw.Draw(overlay)
                draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0), width=3)
                draw.text((x1 + 3, y1 + 3), f"{cls} {score:.2f}", fill=(0, 255, 0))
            if not seg_labels:
                continue
            name = "dfv16_" + img_path.name
            dst_img = OUT / split / "images" / name
            if not dst_img.exists():
                try:
                    os.link(img_path, dst_img)
                except OSError:
                    shutil.copy2(img_path, dst_img)
            with open(OUT / split / "labels" / (Path(name).stem + ".txt"), "w") as f:
                for cls, poly in seg_labels:
                    coords = " ".join(f"{x:.6f} {y:.6f}" for x, y in poly)
                    f.write(f"{cls} {coords}\n")
            stats["images"] += 1
            if stats["images"] <= 12:
                overlay.convert("RGB").save(OUT / "audit" / name)
            if stats["images"] % 50 == 0:
                torch.cuda.empty_cache()
                elapsed = time.time() - started
                print(json.dumps({"images": stats["images"], "objects": stats["objects"], "accepted": stats["accepted"], "rejected": stats["rejected"], "elapsed_s": round(elapsed)}, ensure_ascii=False), flush=True)
    (OUT / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in stats.items() if k != "audit"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
