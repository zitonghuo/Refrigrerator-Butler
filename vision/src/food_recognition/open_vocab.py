from __future__ import annotations

from pathlib import Path

import clip
import numpy as np
import torch
from clip.clip import _transform
from PIL import Image
from ultralytics import YOLO

from . import catalog
from .service import (
    DISPLAY_NAMES_ZH,
    IMAGE_SUFFIXES,
    FoodCandidate,
    RecognitionError,
    RecognitionResult,
    resolve_device,
)


class OpenVocabularyRecognizer:
    """YOLO-World recognizer configured from a caller-supplied food vocabulary."""

    def __init__(
        self,
        weights: str | Path,
        prompts: list[str],
        *,
        label_map: dict[str, str] | None = None,
        classifier_labels: list[str] | None = None,
        device: str = "auto",
        confidence_threshold: float = 0.1,
        iou_threshold: float = 0.5,
        max_detections: int = 300,
        image_size: int = 1280,
        tile_grid: int = 1,
        tile_overlap: float = 0.2,
    ) -> None:
        self.weights = Path(weights).resolve()
        if not self.weights.is_file():
            raise FileNotFoundError(f"Model weights not found: {self.weights}")
        self.prompts = list(dict.fromkeys(prompt.strip() for prompt in prompts if prompt.strip()))
        self.label_map = dict(label_map or {})
        if not self.prompts:
            raise ValueError("The open-vocabulary prompt list cannot be empty.")

        self.device = resolve_device(device)
        self.torch_device = (
            f"cuda:{self.device}" if self.device.isdigit() else self.device
        )
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.max_detections = max_detections
        self.image_size = image_size
        self.tile_grid = max(1, tile_grid)
        self.tile_overlap = min(max(tile_overlap, 0.0), 0.5)
        self.model = YOLO(str(self.weights))
        self.model.set_classes(self.prompts)
        self.classifier_labels = list(dict.fromkeys(classifier_labels or []))
        self.clip_model = None
        self.clip_text_features = None
        if self.classifier_labels:
            clip_path = self.weights.parent / "clip" / "ViT-B-32.pt"
            if not clip_path.is_file():
                raise FileNotFoundError(f"CLIP weights not found: {clip_path}")
            with clip_path.open("rb") as handle:
                self.clip_model = torch.jit.load(
                    handle,
                    map_location=self.torch_device,
                )
            self.clip_preprocess = _transform(224)
            self.clip_model.eval()
            prompt_texts = []
            for label in self.classifier_labels:
                name = label.split("/")[0].replace("-", " ").strip().lower()
                prompt_texts.extend(
                    [
                        f"a photo of {name}",
                        f"a close-up photo of {name}",
                        f"{name}, a food ingredient",
                    ]
                )
            tokens = clip.tokenize(prompt_texts).to(self.torch_device)
            with torch.no_grad():
                features = self.clip_model.encode_text(tokens)
                features = features.reshape(len(self.classifier_labels), 3, -1).mean(dim=1)
                self.clip_text_features = features / features.norm(dim=-1, keepdim=True)

    def _classify_crops(self, image: Image.Image, boxes: list[list[int]]) -> list[tuple[str, float]]:
        if self.clip_model is None or self.clip_text_features is None:
            raise RecognitionError("CLIP crop classification is not configured.")
        crops = []
        for left, top, right, bottom in boxes:
            left = max(0, min(left, image.width - 1))
            top = max(0, min(top, image.height - 1))
            right = max(left + 1, min(right, image.width))
            bottom = max(top + 1, min(bottom, image.height))
            crops.append(self.clip_preprocess(image.crop((left, top, right, bottom))))

        results: list[tuple[str, float]] = []
        with torch.no_grad():
            for start in range(0, len(crops), 64):
                batch = torch.stack(crops[start : start + 64]).to(self.torch_device)
                features = self.clip_model.encode_image(batch)
                features = features / features.norm(dim=-1, keepdim=True)
                probabilities = (100.0 * features @ self.clip_text_features.T).softmax(dim=-1)
                confidences, indices = probabilities.max(dim=-1)
                for confidence, index in zip(confidences, indices):
                    results.append(
                        (
                            self.classifier_labels[int(index.item())],
                            float(confidence.item()),
                        )
                    )
        return results

    def _predict_boxes(
        self,
        source: np.ndarray,
        offset_x: int,
        offset_y: int,
    ) -> list[tuple[int, str, float, list[int]]]:
        predictions = self.model.predict(
            source=source,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            max_det=self.max_detections,
            device=self.device,
            imgsz=self.image_size,
            verbose=False,
        )
        if not predictions or predictions[0].boxes is None:
            return []
        prediction = predictions[0]
        names = prediction.names or self.model.names
        boxes = []
        for box in prediction.boxes:
            class_id = int(box.cls.item())
            raw_label = str(names[class_id])
            label = self.label_map.get(raw_label, raw_label)
            bbox = [int(value) for value in box.xyxy[0].tolist()]
            bbox = [
                bbox[0] + offset_x,
                bbox[1] + offset_y,
                bbox[2] + offset_x,
                bbox[3] + offset_y,
            ]
            boxes.append(
                (
                    class_id,
                    label,
                    round(float(box.conf.item()), 6),
                    bbox,
                )
            )
        return boxes

    @staticmethod
    def _box_iou(first: list[int], second: list[int]) -> float:
        left = max(first[0], second[0])
        top = max(first[1], second[1])
        right = min(first[2], second[2])
        bottom = min(first[3], second[3])
        intersection = max(0, right - left) * max(0, bottom - top)
        first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
        second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
        union = first_area + second_area - intersection
        return intersection / union if union else 0.0

    def _merge_boxes(
        self,
        boxes: list[tuple[int, str, float, list[int]]],
    ) -> list[tuple[int, str, float, list[int]]]:
        kept = []
        for candidate in sorted(boxes, key=lambda item: item[2], reverse=True):
            _, label, _, bbox = candidate
            if any(
                (
                    label == kept_label
                    and self._box_iou(bbox, kept_bbox) >= 0.6
                )
                or self._box_iou(bbox, kept_bbox) >= 0.85
                for _, kept_label, _, kept_bbox in kept
            ):
                continue
            kept.append(candidate)
        return kept

    def predict_image(self, image_path: str | Path) -> RecognitionResult:
        image = Path(image_path).resolve()
        if not image.is_file():
            raise FileNotFoundError(f"Image not found: {image}")
        if image.suffix.lower() not in IMAGE_SUFFIXES:
            raise RecognitionError(f"Unsupported image type: {image.suffix}")

        with Image.open(image) as source_image:
            image_rgb = source_image.convert("RGB")
            width, height = image_rgb.size
            raw_boxes = self._predict_boxes(np.asarray(image_rgb), 0, 0)

            if self.tile_grid > 1:
                tile_width = width / self.tile_grid
                tile_height = height / self.tile_grid
                overlap_x = tile_width * self.tile_overlap
                overlap_y = tile_height * self.tile_overlap
                for row in range(self.tile_grid):
                    for column in range(self.tile_grid):
                        left = max(0, int(column * tile_width - overlap_x))
                        top = max(0, int(row * tile_height - overlap_y))
                        right = min(
                            width,
                            int((column + 1) * tile_width + overlap_x),
                        )
                        bottom = min(
                            height,
                            int((row + 1) * tile_height + overlap_y),
                        )
                        tile = image_rgb.crop((left, top, right, bottom))
                        raw_boxes.extend(
                            self._predict_boxes(np.asarray(tile), left, top)
                        )

            raw_boxes = self._merge_boxes(raw_boxes)
            candidates: list[FoodCandidate] = []

        classifications = []
        if self.classifier_labels and raw_boxes:
            with Image.open(image) as source_image:
                classifications = self._classify_crops(
                    source_image.convert("RGB"),
                    [item[3] for item in raw_boxes],
                )

        if classifications:
            classified_boxes = []
            for index, (class_id, label, detector_confidence, bbox) in enumerate(raw_boxes):
                label, classifier_confidence = classifications[index]
                confidence = round(
                    0.4 * detector_confidence + 0.6 * classifier_confidence,
                    6,
                )
                classified_boxes.append((class_id, label, confidence, bbox))
            raw_boxes = self._merge_boxes(classified_boxes)

        for class_id, label, confidence, bbox in raw_boxes:
            candidates.append(
                FoodCandidate(
                    class_id=class_id,
                    label=label,
                    display_name=catalog.display_name(
                        label,
                        DISPLAY_NAMES_ZH.get(label, ""),
                    ),
                    confidence=confidence,
                    bbox_xyxy=bbox,
                )
            )

        return RecognitionResult(
            schema_version="1.0",
            source_type="photo",
            source=str(image),
            model=str(self.weights),
            device=self.device,
            image_width=int(width),
            image_height=int(height),
            candidates=candidates,
        )
