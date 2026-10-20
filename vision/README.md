# Food Recognition Service

This directory contains the image-based food recognition part extracted from:

- Source: https://github.com/lannguyen0910/food-recognition
- Retrieved: 2026-09-29
- License: MIT

The original repository includes a Flask demo, nutrition analysis, training
utilities, segmentation, classification, and YOLOv5/YOLOv8 detection. This
service only keeps the parts useful for Fridge Butler:

- YOLOv8 image inference
- the upstream detection class configuration
- the upstream pretrained-weight download mapping
- a stable candidate output contract for later receipt and expiry modules

Video frame extraction, cross-frame deduplication, receipt OCR, expiry OCR, and
inventory writes are intentionally not included here.

## Evaluation Dataset

The local LVIS fruit and vegetable evaluation subset is under:

```text
datasets/fruits_vegetables_lvis_eval_v1/
```

It contains 180 manually labeled images and 2,725 object boxes. See
`datasets/README.md` for source, license, validation and baseline results.

## Improved Model

The specialized produce detector is:

```text
weights/fruits_vegetables_yolov8s_v1.pt
```

It was trained on 6,721 images and 63 fruit and vegetable classes. The complete
comparison is in `MODEL_EVALUATION.md`.

## Chinese Fridge Catalog

Serving-time labels are standardized by:

```text
configs/china_fridge_catalog_v1.json
```

The catalog contains 104 common ingredients normally stored in Chinese
households' refrigerators or freezers. It provides:

- Chinese display names
- canonical ingredient IDs
- category and default storage location
- whether the ingredient is countable
- model-label aliases
- English prompts for the open-vocabulary backend
- Chinese aliases, default units, storage locations and reference shelf life

Detailed units, aliases and storage metadata are stored in:

```text
configs/fridge_metadata_v1.json
```

Categories that are uncommon in China, pantry-only, or primarily spices are
filtered from normal service output. Internal model labels may remain English,
but the application returns Chinese names.

## Environment

Python 3.14 is supported by the code. The current machine has an NVIDIA
RTX 5060, so the CUDA environment is recommended:

```powershell
cd 冰箱管家可运行项目\fridge-keeper\vision
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements-torch-cu128.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

For a CPU-only fallback:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-torch-cpu.txt
.\.venv\Scripts\python.exe -m pip install -e .
```

## Model Weights

The upstream repository does not ship weights. Download the YOLOv8 food model:

```powershell
.\.venv\Scripts\python.exe scripts\download_weights.py --model yolov8s
```

The default model path is `weights/yolov8s.pt`.

## Smoke Test

```powershell
.\.venv\Scripts\python.exe -m food_recognition --image samples\watermelon.jpg
```

The command prints JSON containing the model, resolved device, image size, and
detected candidates. A candidate is not written to inventory automatically.

## HTTP Service

The Fridge Butler backend can start this service automatically. It can also be
run separately:

```powershell
.\.venv\Scripts\python.exe -m food_recognition.server `
  --host 127.0.0.1 `
  --port 8770 `
  --device auto
```

The service exposes:

- `GET /health`
- `POST /recognize`

The recognition request and response use the Fridge Butler candidate contract:

```json
{
  "kind": "photo",
  "images": ["base64-image"]
}
```

```json
{
  "candidates": [
    {
      "name": "西瓜",
      "quantity": 1,
      "unit": "个",
      "location": "冷藏",
      "expiry": ""
    }
  ]
}
```

## Standalone Deployment

This directory is self-contained (`src/`, `configs/`, `weights/`, `Dockerfile`) and can be
deployed without the browser demo or the inventory backend.

Environment variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `FRIDGE_VISION_RUNTIME_DIR` | writable dir for YOLO config and extracted frames | `vision/.runtime` |
| `FRIDGE_VISION_TOKEN` | enables `Authorization: Bearer` on `/catalog` and `/recognize` (`/health` and `/` stay open) | empty |
| `FRIDGE_VISION_MAX_BYTES` | request size limit | 28 MB |

CPU container:

```powershell
docker build -t fridge-vision .
docker run --rm -p 8770:8770 -e FRIDGE_VISION_TOKEN=change-me -v fridge-vision-data:/data fridge-vision
```

The image uses CPU inference. For GPU, swap `requirements-torch-cpu.txt` for
`requirements-torch-cu128.txt` and start the container with GPU access. See
`../docs/小程序接入识别服务.md` for the WeChat Mini Program integration notes,
the HTTP contract used by clients, and measured latency.

## Output Contract

```json
{
  "schema_version": "1.0",
  "source_type": "photo",
  "source": "samples/watermelon.jpg",
  "model": "weights/yolov8s.pt",
  "device": "0",
  "image": {
    "width": 768,
    "height": 512
  },
  "candidates": [
    {
      "class_id": 76,
      "label": "Watermelon",
      "display_name": "西瓜",
      "confidence": 0.92,
      "bbox_xyxy": [10, 20, 300, 400]
    }
  ]
}
```

Later modules should add `receipt` and `expiry` sources while preserving the
same candidate review boundary.
