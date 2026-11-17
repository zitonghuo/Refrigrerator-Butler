# -*- coding: utf-8 -*-
"""Prototype: local masks -> numbered overlay -> one GLM-4V call -> counts."""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image
from ultralytics import YOLO

DEFAULT_WEIGHTS = Path(r"E:\Refrigrerator-Butler\Refrigrerator-Butler\vision\weights\fruits_vegetables_yolov8m_seg_expanded_v4.pt")
API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"


def box_iou(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    aa = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
    bb = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    return inter / (aa + bb - inter + 1e-9)


def mask_iou(a, b):
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / (union + 1e-9))


def select_masks(result, conf_threshold=0.35, box_iou_threshold=0.5, mask_iou_threshold=0.45):
    if result.boxes is None:
        return []
    masks = result.masks.data.cpu().numpy() if result.masks is not None else [None] * len(result.boxes)
    candidates = []
    for box, mask in zip(result.boxes, masks):
        if float(box.conf) < conf_threshold:
            continue
        candidates.append({
            "conf": float(box.conf),
            "cls": int(box.cls),
            "box": [float(v) for v in box.xyxy[0].tolist()],
            "mask": mask,
        })
    candidates.sort(key=lambda x: x["conf"], reverse=True)
    kept = []
    for candidate in candidates:
        duplicate = False
        for accepted in kept:
            if box_iou(candidate["box"], accepted["box"]) >= box_iou_threshold:
                duplicate = True
                break
            if candidate["mask"] is not None and accepted["mask"] is not None and mask_iou(candidate["mask"], accepted["mask"]) >= mask_iou_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)
    kept.sort(key=lambda x: (x["box"][1], x["box"][0]))
    return kept


def draw_numbered(image: np.ndarray, masks: list[dict], path: Path):
    canvas = image.copy()
    for index, item in enumerate(masks, 1):
        mask = item["mask"]
        if mask is not None:
            mask_u8 = (mask > 0.5).astype(np.uint8)
            contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(canvas, contours, -1, (0, 255, 0), 2)
        x1, y1, x2, y2 = [int(v) for v in item["box"]]
        label = str(index)
        tw, th = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)[0]
        ty = max(th + 6, y1 - 4)
        cv2.rectangle(canvas, (x1, ty - th - 6), (x1 + tw + 8, ty + 2), (0, 0, 0), -1)
        cv2.putText(canvas, label, (x1 + 4, ty - 3), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)
    cv2.imwrite(str(path), cv2.cvtColor(canvas, cv2.COLOR_RGB2BGR))


def parse_objects(content: str):
    """Parse GLM JSON, tolerating a missing closing bracket before the root brace."""
    fenced = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    raw_candidates = [fenced.group(1)] if fenced else [content]
    raw_candidates += re.findall(r"\{[\s\S]*\}", content)
    for raw in raw_candidates:
        raw = raw.strip()
        variants = [raw]
        if raw.endswith("}") and raw.count("[") > raw.count("]"):
            variants.append(raw[:-1] + "]" + raw[-1])
        if raw.endswith("}") and raw.count("{") > raw.count("}"):
            variants.append(raw + "}")
        for candidate in variants:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict) and "objects" in parsed:
                    return parsed
            except json.JSONDecodeError:
                continue
    raise RuntimeError("GLM 未返回可解析的 objects JSON: " + content[:300])


def call_glm(image_path: Path, count: int, key: str):
    img = Image.open(image_path).convert("RGB")
    img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    from io import BytesIO
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=88)
    b64 = base64.b64encode(buf.getvalue()).decode()
    prompt = (
        "图中用绿色细轮廓和数字 1..%d 标记了已经分割出的食材。"
        "请只根据画面判断每个编号对应的食材中文名称。"
        "不要遗漏编号，不要重复编号，不要输出不存在的编号；不确定时写“不确定”。"
        "只输出 JSON：{\"objects\":[{\"id\":1,\"name\":\"番茄\"}]}"
    ) % count
    import time
    response = None
    for attempt in range(4):
        response = requests.post(
            API_URL,
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
            json={
                "model": "glm-4.6v-flash",
                "stream": False,
                "max_tokens": 1200,
                "do_sample": False,
                "messages": [{"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
                    {"type": "text", "text": prompt},
                ]}],
            },
            timeout=45,
        )
        if response.status_code == 429:
            try:
                error = response.json().get("error", {})
            except Exception:
                error = {}
            if error.get("code") == "1113":
                raise RuntimeError("GLM 余额不足或无可用资源包: " + str(error.get("message", "")))
            time.sleep(8 * (attempt + 1))
            continue
        response.raise_for_status()
        break
    else:
        raise RuntimeError("GLM 连续返回 429 限流，请稍后重试")
    body = response.json()
    content = body["choices"][0]["message"]["content"]
    value = parse_objects(content)
    objects = value.get("objects", [])
    mapping = {}
    for item in objects:
        try:
            mapping[int(item["id"])] = str(item.get("name", "")).strip()
        except (KeyError, TypeError, ValueError):
            continue
    return {i: mapping.get(i, "不确定") for i in range(1, count + 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", nargs="+", required=True)
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS))
    parser.add_argument("--out", default=r"E:\Refrigrerator-Butler\Refrigrerator-Butler\vision\outputs\numbered_glm")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.weights)
    key = os.environ.get("ZHIPU_API_KEY", "").strip()
    if not args.dry_run and not key:
        raise SystemExit("ZHIPU_API_KEY is not set; use --dry-run or set it in the environment")
    records = []
    for index, raw in enumerate(args.images):
        image_path = Path(raw)
        if index and not args.dry_run:
            time.sleep(10)
        image = cv2.imread(str(image_path))
        if image is None:
            raise FileNotFoundError(image_path)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        result = model.predict(source=str(image_path), conf=0.35, iou=0.5, imgsz=640, verbose=False, device="0")[0]
        masks = select_masks(result)
        numbered = out / (image_path.stem + "_numbered.jpg")
        draw_numbered(image, masks, numbered)
        mapping = {} if args.dry_run else call_glm(numbered, len(masks), key)
        counts = {}
        for name in mapping.values():
            counts[name] = counts.get(name, 0) + 1
        record = {
            "image": str(image_path),
            "numbered": str(numbered),
            "mask_count": len(masks),
            "mapping": mapping,
            "counts": counts,
        }
        records.append(record)
        print(json.dumps(record, ensure_ascii=False, indent=2))
    (out / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
