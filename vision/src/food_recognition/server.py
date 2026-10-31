from __future__ import annotations

import argparse
import base64
import binascii
import json
import os
import secrets
import shutil
import traceback
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .hybrid import HybridFoodRecognizer
from . import catalog
from .service import DEFAULT_WEIGHTS, RUNTIME_CONFIG_DIR, SERVICE_ROOT, FoodRecognizer


GENERIC_LABELS = {"food", "food-drinks"}
# 运行期目录可用 FRIDGE_VISION_RUNTIME_DIR 指定，容器里挂载可写卷即可。
FRAME_ROOT = RUNTIME_CONFIG_DIR / "frames"
FRAME_ROOT.mkdir(parents=True, exist_ok=True)
MAX_REQUEST_BYTES = int(
    os.environ.get("FRIDGE_VISION_MAX_BYTES", str(28 * 1024 * 1024))
)
# 可选鉴权：面向公网部署时设置，小程序/后端在 Authorization 头里带上 Bearer。
SERVICE_TOKEN = os.environ.get("FRIDGE_VISION_TOKEN", "").strip()


def image_suffix(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"BM"):
        return ".bmp"
    return ".jpg"


def aggregate_candidates(
    detections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge repeated labels while preserving the maximum simultaneous count."""
    if not detections:
        return []

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for detection in detections:
        label = detection["label"]
        if label not in GENERIC_LABELS:
            grouped[detection["display_name"]].append(detection)

    candidates = []
    for name, items in grouped.items():
        best = max(items, key=lambda item: item["confidence"])
        catalog_item = catalog.find_class(best["label"]) or {}
        candidates.append(
            {
                "name": name,
                "quantity": len(items),
                "unit": catalog_item.get("default_unit", "个"),
                "location": catalog_item.get("default_storage", "冷藏"),
                "expiry": "",
                "confidence": best["confidence"],
                "bbox_xyxy": best["bbox_xyxy"],
                "canonical_id": catalog_item.get("id", best["label"]),
                "category": catalog_item.get("category", ""),
                "aliases_zh": catalog_item.get("aliases_zh", []),
                "storage_options": catalog_item.get("storage", ["冷藏"]),
                "shelf_life_days": catalog_item.get("shelf_life_days", {}),
                "countable": catalog_item.get("countable", True),
            }
        )
    return sorted(candidates, key=lambda item: item["confidence"], reverse=True)


def recognize_payload(
    recognizer: FoodRecognizer,
    payload: dict[str, Any],
) -> dict[str, Any]:
    kind = payload.get("kind")
    if kind not in {"photo", "video"}:
        raise ValueError("当前本地模型只支持照片和视频，小票识别尚未接入")

    images = payload.get("images")
    if not isinstance(images, list) or not images:
        raise ValueError("没有收到可识别的图片")
    if kind == "photo" and len(images) != 1:
        raise ValueError("照片入口只能提交一张图片")

    per_frame: list[list[dict[str, Any]]] = []
    root = FRAME_ROOT / f"request-{secrets.token_hex(8)}"
    root.mkdir(parents=True, exist_ok=False)
    try:
        for index, encoded in enumerate(images):
            if not isinstance(encoded, str) or not encoded:
                raise ValueError("图片数据格式不正确")
            raw = base64.b64decode(encoded, validate=True)
            image_path = root / f"frame-{index:03d}{image_suffix(raw)}"
            image_path.write_bytes(raw)
            result = recognizer.predict_image(image_path)
            per_frame.append([candidate.__dict__ for candidate in result.candidates])
    finally:
        shutil.rmtree(root, ignore_errors=True)

    # For video frames, use the largest simultaneous count for each label.
    # This avoids multiplying one food item by the number of sampled frames.
    if kind == "video" and per_frame:
        combined: list[dict[str, Any]] = []
        all_names = {
            candidate["display_name"]
            for frame in per_frame
            for candidate in frame
            if candidate["label"] not in GENERIC_LABELS
        }
        for name in all_names:
            matching_frames: list[list[dict[str, Any]]] = []
            for frame in per_frame:
                matches = [
                    candidate
                    for candidate in frame
                    if candidate["display_name"] == name
                ]
                if matches:
                    matching_frames.append(matches)
            if not matching_frames:
                continue
            best_frame = max(matching_frames, key=len)
            combined.extend(best_frame)
        detections = combined
    else:
        detections = [candidate for frame in per_frame for candidate in frame]

    return {
        "candidates": aggregate_candidates(detections),
        "meta": {
            "model": str(recognizer.weights),
            "device": recognizer.device,
            "frames": len(images),
        },
    }


class VisionHandler(BaseHTTPRequestHandler):
    recognizer: FoodRecognizer

    def log_message(self, *args: Any) -> None:
        return

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self) -> bool:
        if not SERVICE_TOKEN:
            return True
        header = self.headers.get("Authorization", "")
        if secrets.compare_digest(header, "Bearer " + SERVICE_TOKEN):
            return True
        self.send_json(401, {"error": "识别服务鉴权失败"})
        return False

    def do_GET(self) -> None:
        if self.path == "/health":
            # 健康检查保持开放，方便容器探针与后端自动发现。
            self.send_json(
                200,
                {
                    "status": "ok",
                    "model": str(self.recognizer.weights),
                    "device": self.recognizer.device,
                    "runtime": str(RUNTIME_CONFIG_DIR),
                    "auth_required": bool(SERVICE_TOKEN),
                },
            )
            return
        if self.path == "/":
            self.send_json(
                200,
                {
                    "service": "fridge-food-recognition",
                    "endpoints": ["GET /health", "GET /catalog", "POST /recognize"],
                    "kinds": ["photo", "video"],
                    "auth_required": bool(SERVICE_TOKEN),
                },
            )
            return
        if not self.authorized():
            return
        if self.path == "/catalog":
            self.send_json(200, catalog.export_catalog())
            return
        self.send_json(404, {"error": "接口不存在"})

    def do_POST(self) -> None:
        if self.path != "/recognize":
            self.send_json(404, {"error": "接口不存在"})
            return
        if not self.authorized():
            return

        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= MAX_REQUEST_BYTES:
                raise ValueError("文件过大，请使用 20 MB 以内的素材")
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict):
                raise ValueError("请求必须是对象")
            self.send_json(200, recognize_payload(self.recognizer, payload))
        except (ValueError, TypeError, binascii.Error, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error) or "识别请求格式不正确"})
        except Exception:
            traceback.print_exc()
            self.send_json(500, {"error": "本地模型识别失败，请查看识别服务日志"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local food recognition HTTP service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--weights", type=Path, default=DEFAULT_WEIGHTS)
    parser.add_argument(
        "--produce-weights",
        type=Path,
        default=SERVICE_ROOT / "weights" / "fruits_vegetables_yolov8s_cn_v2.pt",
    )
    parser.add_argument(
        "--backend",
        choices=["hybrid", "general", "world"],
        default="hybrid",
    )
    parser.add_argument(
        "--world-weights",
        type=Path,
        default=SERVICE_ROOT / "weights" / "yolov8s-worldv2.pt",
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--conf", type=float, default=0.15)
    parser.add_argument("--iou", type=float, default=0.5)
    parser.add_argument("--imgsz", type=int, default=640)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.backend == "hybrid":
        recognizer = HybridFoodRecognizer(
            args.produce_weights,
            args.weights,
            device=args.device,
            produce_confidence=args.conf,
            general_confidence=0.25,
            iou_threshold=args.iou,
            image_size=args.imgsz,
        )
    elif args.backend == "world":
        from .open_vocab import OpenVocabularyRecognizer

        prompts, label_map = catalog.world_vocabulary()
        recognizer = OpenVocabularyRecognizer(
            args.world_weights,
            prompts=prompts,
            label_map=label_map,
            device=args.device,
            confidence_threshold=args.conf,
            iou_threshold=args.iou,
            image_size=args.imgsz,
        )
    else:
        recognizer = FoodRecognizer(
            args.weights,
            device=args.device,
            confidence_threshold=args.conf,
            iou_threshold=args.iou,
            image_size=args.imgsz,
        )
    VisionHandler.recognizer = recognizer
    server = ThreadingHTTPServer((args.host, args.port), VisionHandler)
    print(
        f"Food recognition service ready on http://{args.host}:{args.port} "
        f"(device={recognizer.device}, runtime={RUNTIME_CONFIG_DIR}, "
        f"auth={'on' if SERVICE_TOKEN else 'off'})",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
