from food_recognition.service import FoodCandidate, RecognitionResult
from food_recognition.server import aggregate_candidates, image_suffix
from food_recognition import catalog


def test_result_contract_is_stable() -> None:
    result = RecognitionResult(
        schema_version="1.0",
        source_type="photo",
        source="sample.jpg",
        model="weights/yolov8s.pt",
        device="cpu",
        image_width=640,
        image_height=480,
        candidates=[
            FoodCandidate(
                class_id=1,
                label="Apple",
                display_name="苹果",
                confidence=0.9,
                bbox_xyxy=[1, 2, 3, 4],
            )
        ],
    )

    payload = result.to_dict()

    assert payload["image"] == {"width": 640, "height": 480}
    assert payload["candidates"][0]["display_name"] == "苹果"
    assert "image_width" not in payload
    assert "image_height" not in payload


def test_candidates_are_merged_by_display_name() -> None:
    candidates = aggregate_candidates(
        [
            {
                "label": "Apple",
                "display_name": "苹果",
                "confidence": 0.8,
                "bbox_xyxy": [1, 2, 3, 4],
            },
            {
                "label": "Apple",
                "display_name": "苹果",
                "confidence": 0.9,
                "bbox_xyxy": [5, 6, 7, 8],
            },
            {
                "label": "food",
                "display_name": "通用食物",
                "confidence": 0.99,
                "bbox_xyxy": [9, 10, 11, 12],
            },
        ]
    )

    assert candidates == [
        {
            "name": "苹果",
            "quantity": 2,
            "unit": "个",
            "location": "冷藏",
            "expiry": "",
            "confidence": 0.9,
            "bbox_xyxy": [5, 6, 7, 8],
            "canonical_id": "apple",
            "category": "水果",
            "aliases_zh": ["苹果"],
            "storage_options": ["冷藏"],
            "shelf_life_days": {"冷藏": [3, 7]},
            "countable": True,
        }
    ]


def test_image_signature_detection() -> None:
    assert image_suffix(b"\x89PNG\r\n\x1a\nrest") == ".png"
    assert image_suffix(b"\xff\xd8\xffrest") == ".jpg"
    assert image_suffix(b"RIFF1234WEBPrest") == ".webp"


def test_chinese_fridge_catalog_filters_non_fridge_items() -> None:
    assert catalog.display_name("apple") == "苹果"
    assert catalog.display_name("Apple") == "苹果"
    assert catalog.is_fridge_candidate("Milk") is True
    assert catalog.is_fridge_candidate("Hot-dog") is False
    assert catalog.is_fridge_candidate("Wine") is False


def test_catalog_contains_chinese_metadata() -> None:
    data = catalog.export_catalog()
    classes = {item["id"]: item for item in data["classes"]}

    assert len(classes) >= 100
    assert classes["tomato"]["aliases_zh"] == ["番茄", "西红柿"]
    assert classes["tomato"]["default_unit"] == "个"
    assert classes["chicken_breast"]["default_storage"] == "冷冻"
    assert classes["dumpling"]["shelf_life_days"]["冷冻"] == [90, 180]
    assert "肉桂" not in classes
