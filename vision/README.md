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

## Datasets and Training Artifacts Are Not in the Repository

To keep the Git repository small, `datasets/` (about 5 GB) and `runs/` (about
240 MB) are stored outside the project:

```text
E:\fridge-keeper-datasets\
  datasets\
  runs\
```

The scripts in `scripts/` still expect `datasets/` relative to this directory.
Restore it when you need to evaluate or retrain:

```powershell
# 直接移回（推荐，同盘瞬时完成）
Move-Item E:\fridge-keeper-datasets\datasets .\datasets

# 或者建目录联接，不占用仓库空间
New-Item -ItemType Junction -Path .\datasets -Target E:\fridge-keeper-datasets\datasets
```

Model weights (`weights/*.pt`, about 520 MB) are also excluded from Git; download
them with `scripts/download_weights.py` or keep a local copy. The API service
needs `weights/yolov8s.pt` to start.

## Improved Model

The specialized produce detector is:

```text
weights/fruits_vegetables_yolov8s_cn_v2.pt
```

It was trained on 6,721 images and 63 fruit and vegetable classes, then pruned to
47 classes for Chinese household use. Rare or duplicated classes such as
chickpea, artichoke, brussels sprouts, blackberry, raspberry, coconut, lime,
fig, prune, turnip, clementine and duplicate `Strawberry`/`Tomato` outputs are
removed from the class branch. The original 63-class weights are kept as
`fruits_vegetables_yolov8s_v1.pt` for comparison. Weights are excluded from Git;
after downloading the v1 weights, regenerate the Chinese-household model with:

```powershell
python scripts/prune_rare_classes.py `
  --weights weights/fruits_vegetables_yolov8s_v1.pt `
  --config configs/china_household_filter_v1.json `
  --output weights/fruits_vegetables_yolov8s_cn_v2.pt
```

The server's `--produce-weights` default points at this v2 file.

## Merged Chinese-Fridge Training Set (2026-10-31)

Because the produce detector has no meat, egg, tofu or staple classes, the next
baseline merges FoodInsSeg with the existing LVIS produce split:

```powershell
python scripts/build_china_fridge_dataset.py `
  --foodinsseg E:\fridge-keeper-datasets\datasets\FoodInsSeg `
  --lvis E:\fridge-keeper-datasets\datasets\fruits_vegetables_lvis_full `
  --output E:\fridge-keeper-datasets\datasets\china_fridge_v1 `
  --config configs/china_fridge_classes_v1.json
```

Result:

```text
71 classes
train: 10,532 images / 195,071 boxes
val:    1,172 images /  23,972 boxes
test:   2,315 images /  27,848 boxes
```

FoodInsSeg is **CC BY-NC-SA 4.0, non-commercial research only**; see
`THIRD_PARTY_NOTICES.md`. Images/labels stay outside the repository.

Train with:

```powershell
python scripts/train_detector.py `
  --model weights/yolov8s.pt `
  --data E:\fridge-keeper-datasets\datasets\china_fridge_v1\data.yaml `
  --epochs 20 --imgsz 640 --batch 8 --device 0 --amp `
  --name china_fridge_v1_baseline
```

Evaluate the held-out test split:

```powershell
python scripts/evaluate_unified.py `
  --weights runs/china_fridge_v1_v2/weights/best.pt `
  --split test
```

The 20-epoch baseline reached 74.0% recall / 79.1% class accuracy on the 180
LVIS test images, and 53.3% / 80.0% on the 2,135 FoodInsSeg test images. It adds
meat/egg/tofu classes but those are still weak; see
`outputs/china_fridge_v1_test_report.md`.

### Produce-only follow-up

Filter the merged set back to the 47 produce classes:

```powershell
python scripts/build_produce_dataset.py `
  --source E:\fridge-keeper-datasets\datasets\china_fridge_v1 `
  --weights weights/fruits_vegetables_yolov8s_cn_v2.pt `
  --output E:\fridge-keeper-datasets\datasets\china_fridge_produce_v1
```

Fine-tune from v2 for 15 epochs, then evaluate on the held-out test split:

```powershell
python scripts/train_detector.py `
  --model weights/fruits_vegetables_yolov8s_cn_v2.pt `
  --data E:\fridge-keeper-datasets\datasets\china_fridge_produce_v1\data.yaml `
  --epochs 15 --imgsz 640 --batch 8 --device 0 --amp `
  --name china_fridge_produce_v3

python scripts/evaluate_unified.py `
  --dataset E:\fridge-keeper-datasets\datasets\china_fridge_produce_v1 `
  --weights runs/china_fridge_produce_v3/weights/best.pt --split test
```

v3 raises combined-test class accuracy from 71.9% to 86.3% and lowers false
positives from 7.26 to 5.54, but is about 1.4 points lower on the 180 LVIS
images. Keep v2 as serving default until a real-fridge test; see
`outputs/produce_v3_test_report.md`.

### Crop classifier upper bound (negative result)

A 45-class ResNet18 was trained on 37,476 GT-box crops. Test Top-1 was only
55.7% (Top-3 75.0%), far below the detector's 86.3% class accuracy on matched
boxes. Do not integrate this crop stage; see
`outputs/crop_classifier_report.md`.


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
