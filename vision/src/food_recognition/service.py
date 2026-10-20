from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parents[2]
# 运行期文件（YOLO 配置、抽帧临时目录）默认放在项目内，可用环境变量改到可写目录，
# 便于把识别服务单独部署到容器或只读文件系统。
RUNTIME_CONFIG_DIR = Path(
    os.environ.get("FRIDGE_VISION_RUNTIME_DIR", str(SERVICE_ROOT / ".runtime"))
).resolve()
RUNTIME_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault(
    "YOLO_CONFIG_DIR",
    str(RUNTIME_CONFIG_DIR),
)

from ultralytics import YOLO

from . import catalog


DEFAULT_WEIGHTS = SERVICE_ROOT / "weights" / "yolov8s.pt"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

# The upstream detector uses English class names. The Chinese labels are only
# presentation metadata and can be expanded without retraining the model.
DISPLAY_NAMES_ZH = {
    "almond": "杏仁",
    "apple": "苹果",
    "Apple": "苹果",
    "apricot": "杏",
    "artichoke": "洋蓟",
    "asparagus": "芦笋",
    "avocado": "牛油果",
    "banana": "香蕉",
    "Banana": "香蕉",
    "bean curd/tofu": "豆腐",
    "bell pepper/capsicum": "甜椒",
    "blackberry": "黑莓",
    "blueberry": "蓝莓",
    "broccoli": "西兰花",
    "brussels sprouts": "抱子甘蓝",
    "cantaloup/cantaloupe": "哈密瓜",
    "carrot": "胡萝卜",
    "cauliflower": "花椰菜",
    "cayenne/cayenne spice/cayenne pepper/cayenne pepper spice/red pepper/red pepper": "辣椒",
    "celery": "芹菜",
    "cherry": "樱桃",
    "chickpea/garbanzo": "鹰嘴豆",
    "chili/chili vegetable/chili pepper/chili pepper vegetable/chilli/chilli vegetable/chilly/chilly": "辣椒",
    "clementine": "克莱门氏小柑橘",
    "coconut/cocoanut": "椰子",
    "cucumber/cuke": "黄瓜",
    "date/date fruit": "枣",
    "edible corn/corn/maize": "玉米",
    "eggplant/aubergine": "茄子",
    "fig/fig fruit": "无花果",
    "garlic/ail": "大蒜",
    "ginger/gingerroot": "生姜",
    "gourd": "葫芦瓜",
    "grape": "葡萄",
    "green bean": "青豆",
    "green onion/spring onion/scallion": "小葱",
    "kiwi fruit": "猕猴桃",
    "lemon": "柠檬",
    "lettuce": "生菜",
    "lime": "青柠",
    "mandarin orange": "橘子",
    "melon": "甜瓜",
    "mushroom": "蘑菇",
    "onion": "洋葱",
    "orange/orange fruit": "橙子",
    "papaya": "木瓜",
    "pea/pea food": "豌豆",
    "peach": "桃子",
    "pear": "梨",
    "persimmon": "柿子",
    "pickle": "腌黄瓜",
    "pineapple": "菠萝",
    "potato": "土豆",
    "prune": "李子干",
    "pumpkin": "南瓜",
    "radish/daikon": "萝卜",
    "raspberry": "树莓",
    "strawberry": "草莓",
    "sweet potato": "红薯",
    "tomato": "番茄",
    "turnip": "芜菁",
    "watermelon": "西瓜",
    "zucchini/courgette": "西葫芦",
    "Beer": "啤酒",
    "Bell-pepper": "甜椒",
    "Bread": "面包",
    "Broccoli": "西兰花",
    "Cabbage": "卷心菜",
    "Carrot": "胡萝卜",
    "Cheese": "奶酪",
    "Coffee": "咖啡",
    "Cucumber": "黄瓜",
    "Egg": "鸡蛋",
    "Fruit": "水果",
    "Grape": "葡萄",
    "Juice": "果汁",
    "Lemon": "柠檬",
    "Mango": "芒果",
    "Milk": "牛奶",
    "Mushroom": "蘑菇",
    "Orange": "橙子",
    "Peach": "桃子",
    "Pear": "梨",
    "Pineapple": "菠萝",
    "Potato": "土豆",
    "Pumpkin": "南瓜",
    "Radish": "萝卜",
    "Strawberry": "草莓",
    "Tea": "茶",
    "Tomato": "番茄",
    "Vegetable": "蔬菜",
    "Watermelon": "西瓜",
    "Wine": "葡萄酒",
    "Zucchini": "西葫芦",
}


class RecognitionError(RuntimeError):
    """Raised when an image cannot be recognized."""


@dataclass(frozen=True)
class FoodCandidate:
    class_id: int
    label: str
    display_name: str
    confidence: float
    bbox_xyxy: list[int]


@dataclass(frozen=True)
class RecognitionResult:
    schema_version: str
    source_type: str
    source: str
    model: str
    device: str
    image_width: int
    image_height: int
    candidates: list[FoodCandidate]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["image"] = {
            "width": result.pop("image_width"),
            "height": result.pop("image_height"),
        }
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)


def resolve_device(requested: str = "auto") -> str:
    if requested != "auto":
        return requested

    try:
        import torch
    except ImportError:
        return "cpu"

    return "0" if torch.cuda.is_available() else "cpu"


class FoodRecognizer:
    """Thin, reusable YOLOv8 wrapper with a service-friendly output contract."""

    def __init__(
        self,
        weights: str | Path = DEFAULT_WEIGHTS,
        *,
        device: str = "auto",
        confidence_threshold: float = 0.25,
        iou_threshold: float = 0.5,
        max_detections: int = 300,
        image_size: int = 640,
    ) -> None:
        self.weights = Path(weights).resolve()
        if not self.weights.is_file():
            raise FileNotFoundError(
                f"Model weights not found: {self.weights}. "
                "Run scripts/download_weights.py first."
            )

        self.device = resolve_device(device)
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.max_detections = max_detections
        self.image_size = image_size
        self.model = YOLO(str(self.weights))

    def predict_image(self, image_path: str | Path) -> RecognitionResult:
        image = Path(image_path).resolve()
        if not image.is_file():
            raise FileNotFoundError(f"Image not found: {image}")
        if image.suffix.lower() not in IMAGE_SUFFIXES:
            raise RecognitionError(
                f"Unsupported image type: {image.suffix}. "
                f"Expected one of: {', '.join(sorted(IMAGE_SUFFIXES))}"
            )

        predictions = self.model.predict(
            source=str(image),
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            max_det=self.max_detections,
            device=self.device,
            imgsz=self.image_size,
            verbose=False,
        )
        if not predictions:
            raise RecognitionError("The model returned no prediction result.")

        prediction = predictions[0]
        height, width = prediction.orig_shape
        names = prediction.names or self.model.names
        candidates: list[FoodCandidate] = []

        if prediction.boxes is not None:
            for box in prediction.boxes:
                class_id = int(box.cls.item())
                label = str(names[class_id])
                candidates.append(
                    FoodCandidate(
                        class_id=class_id,
                        label=label,
                        display_name=catalog.display_name(
                            label,
                            DISPLAY_NAMES_ZH.get(label, ""),
                        ),
                        confidence=round(float(box.conf.item()), 6),
                        bbox_xyxy=[
                            int(value) for value in box.xyxy[0].tolist()
                        ],
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
