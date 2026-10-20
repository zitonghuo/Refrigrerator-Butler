from __future__ import annotations

from pathlib import Path

from . import catalog
from .service import FoodCandidate, FoodRecognizer, RecognitionResult


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
        device: str = "auto",
        produce_confidence: float = 0.15,
        general_confidence: float = 0.25,
        iou_threshold: float = 0.5,
        max_detections: int = 300,
        image_size: int = 640,
    ) -> None:
        self.produce = FoodRecognizer(
            produce_weights,
            device=device,
            confidence_threshold=produce_confidence,
            iou_threshold=iou_threshold,
            max_detections=max_detections,
            image_size=image_size,
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
        existing_names = {candidate.display_name for candidate in merged}

        for candidate in general_result.candidates:
            if not catalog.is_fridge_candidate(candidate.label):
                continue
            if candidate.display_name in existing_names:
                continue
            if any(
                box_iou(candidate.bbox_xyxy, existing.bbox_xyxy) >= 0.6
                for existing in merged
            ):
                continue
            merged.append(candidate)
            existing_names.add(candidate.display_name)

        merged.sort(key=lambda candidate: candidate.confidence, reverse=True)
        return RecognitionResult(
            schema_version="1.0",
            source_type="photo",
            source=produce_result.source,
            model=f"{produce_result.model}; {general_result.model}",
            device=self.device,
            image_width=produce_result.image_width,
            image_height=produce_result.image_height,
            candidates=merged,
        )
