from __future__ import annotations

from pathlib import Path

from . import catalog
from .service import FoodCandidate, FoodRecognizer, RecognitionResult


SCENE_LABELS = ("apple", "banana", "broccoli", "carrot", "orange")


def box_iou(first: list[int], second: list[int]) -> float:
    left = max(first[0], second[0])
    top = max(first[1], second[1])
    right = min(first[2], second[2])
    bottom = min(first[3], second[3])
    intersection = max(0, right - left) * max(0, bottom - top)
    first_area = max(0, first[2] - first[0]) * max(0, first[3] - first[1])
    second_area = max(0, second[2] - second[0]) * max(0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


class HybridFoodRecognizer:
    """Combine a specialized produce detector with the broader baseline model."""

    def __init__(
        self,
        produce_weights: str | Path,
        general_weights: str | Path,
        *,
        scene_weights: str | Path | None = None,
        device: str = "auto",
        produce_confidence: float = 0.15,
        general_confidence: float = 0.25,
        iou_threshold: float = 0.5,
        max_detections: int = 300,
        image_size: int = 640,
        agnostic_nms: bool = False,
        augment: bool = False,
    ) -> None:
        self.produce = FoodRecognizer(
            produce_weights,
            device=device,
            confidence_threshold=produce_confidence,
            iou_threshold=iou_threshold,
            max_detections=max_detections,
            image_size=image_size,
            agnostic_nms=agnostic_nms,
            augment=augment,
        )
        self.general = FoodRecognizer(
            general_weights,
            device=device,
            confidence_threshold=general_confidence,
            iou_threshold=iou_threshold,
            max_detections=max_detections,
            image_size=image_size,
        )
        self.weights = self.produce.weights
        self.scene = None
        if scene_weights is not None:
            self.scene = FoodRecognizer(
                scene_weights, device=device, confidence_threshold=general_confidence,
                iou_threshold=iou_threshold, image_size=image_size,
                max_detections=max_detections,
            )
            if not set(SCENE_LABELS).issubset(self.scene.model.names.values()):
                raise ValueError("Scene weights must include all five COCO produce labels")
        self.device = self.produce.device
        self.image_size = image_size

    def predict_image(self, image_path: str | Path) -> RecognitionResult:
        produce_result = self.produce.predict_image(image_path)
        general_result = self.general.predict_image(image_path)
        merged = [
            candidate
            for candidate in produce_result.candidates
            if catalog.is_fridge_candidate(candidate.label)
        ]
        produce_candidates = tuple(merged)

        for candidate in general_result.candidates:
            if not catalog.is_fridge_candidate(candidate.label):
                continue
            if any(
                box_iou(candidate.bbox_xyxy, existing.bbox_xyxy) >= 0.6
                for existing in produce_candidates
            ):
                continue
            merged.append(candidate)

        model_paths = [produce_result.model, general_result.model]
        if self.scene is not None:
            scene_result = self.scene.predict_image(image_path)
            scene_names = {catalog.display_name(label) for label in SCENE_LABELS}
            merged = [item for item in merged if item.display_name not in scene_names]
            merged.extend(item for item in scene_result.candidates if item.label in SCENE_LABELS)
            model_paths.append(scene_result.model)
        merged.sort(key=lambda candidate: candidate.confidence, reverse=True)
        return RecognitionResult(
            schema_version="1.0",
            source_type="photo",
            source=produce_result.source,
            model="; ".join(model_paths),
            device=self.device,
            image_width=produce_result.image_width,
            image_height=produce_result.image_height,
            candidates=merged,
        )
