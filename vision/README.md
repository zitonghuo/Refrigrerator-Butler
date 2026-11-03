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
ruits_vegetables_lvis_full and ruits_vegetables_lvis_eval_v1.
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

## Scope

This service only recognizes **raw produce before it is put into the fridge**.
Cooked dishes, plated meals and restaurant photos are out of scope and have
been removed from the training data and weights. Ingredient photos taken on a
table or shelf are in scope. The serving default is the 47-class produce model;
meat, eggs, tofu and packaged food are handled manually or by a separate future
module.

Only raw-produce training/evaluation data is kept outside the repository:

`fruits_vegetables_lvis_full`, `fruits_vegetables_lvis_eval_v1`, and the
IntAli produce subset.

### COCO supplement (negative result)

975 COCO raw-produce images (apple, banana, orange, broccoli, carrot) were added
to LVIS; COCO images containing pizza, sandwiches, hot dogs, donuts or cake were
excluded. Fine-tuning v2 on the merged set did not improve the LVIS held-out
test: with 15 epochs, v2 stayed at 72.1% recall / 59.6% end-to-end, while the
supplemented model reached 67.3% / 54.4% (or 72.9% / 57.9% at conf 0.10).
Keep v2; see `outputs/raw_produce_coco_report.md`.

### Cross-style test (LVIS vs COCO)

A held-out 322-image cross-style test was built from LVIS (180) and COCO (142)
raw produce; COCO images used for testing were not in training.

| Test style | Model | Recall | Class | End-to-end | FP/image |
| --- | --- | ---: | ---: | ---: | ---: |
| LVIS | v2 | 72.1% | 82.6% | 59.6% | 10.03 |
| COCO | v2 | 51.6% | 91.3% | 47.1% | 24.24 |
| LVIS | v2 + style aug | 66.2% | 76.4% | 50.6% | 8.28 |
| COCO | v2 + style aug | 52.9% | 93.7% | 49.5% | 24.18 |

The COCO style is clearly harder for v2. Strong colour/geometry augmentation
improved COCO end-to-end by only 2.4 points while dropping LVIS by 9 points, so
it is not adopted. Multi-style real photos are still needed; see
`outputs/cross_style_report.md`.

### IntAli target-style fine-tune

IntAli Food Dataset (4,019 images, 41 contributors, ingredients on tables or
shelves) was filtered to 26 produce classes: 1,130 train, 125 val, 382 test.

| Test | Model | Recall | Class | End-to-end | FP/image |
| --- | --- | ---: | ---: | ---: | ---: |
| IntAli | v2 | 75.2% | 57.6% | 43.3% | 4.18 |
| IntAli | IntAli-only fine-tune | 89.7% | 91.2% | 81.8% | 0.72 |
| IntAli | mixed fine-tune | **91.0%** | **91.0%** | **82.8%** | **1.52** |
| LVIS | mixed fine-tune | 46.3% | 74.1% | 34.3% | 5.18 |

Target-style data gives the largest gain so far, but IntAli-only training
forgets LVIS (9.1% recall). Mixed training keeps the target gain and partially
retains source data. Candidate weights:
`runs/raw_mixed_v1/weights/best.pt`; the serving default remains v2 until a
Chinese countertop test. See `outputs/intali_report.md`.

### YOLOv8m-seg vs YOLOv8s (fair comparison)

Both models were trained from COCO weights on the same mixed data, same 15
epochs, 640 input, batch 8, first 10 layers frozen, lr 0.001. IntAli masks are
used for m-seg; LVIS/COCO boxes are converted to rectangular polygons.

| Test | Model | Recall | Class | End-to-end | FP/image |
| --- | --- | ---: | ---: | ---: | ---: |
| IntAli | YOLOv8s | 89.8% | 90.2% | 81.0% | 1.08 |
| IntAli | **YOLOv8m-seg** | **91.1%** | **93.3%** | **85.0%** | **0.80** |
| LVIS | YOLOv8s | 46.5% | 70.3% | **32.7%** | **5.23** |
| LVIS | YOLOv8m-seg | **47.8%** | 66.5% | 31.8% | 5.37 |
| COCO | YOLOv8s | 50.6% | 90.1% | 45.6% | **20.36** |
| COCO | **YOLOv8m-seg** | **53.7%** | **93.2%** | **50.1%** | 21.34 |

m-seg is +4.0 points end-to-end on IntAli and +4.5 on COCO, with a slight LVIS
trade-off (-0.9). Cost: 52.3 MB vs 21.5 MB, ~6.2 ms vs ~2.0 ms validation
inference. Candidate weights:
`runs/fair_v8mseg_mixed_15e/weights/best.pt`; see
`outputs/fair_v8s_vs_v8mseg.md`.

An IntAli-only m-seg model reached 86.6% end-to-end but forgot LVIS almost
entirely; the mixed model is the better replacement candidate.

### Automatic clean filter (negative result)

Removing prepared/processed categories left 557 train / 164 test images.
The clean-trained m-seg fell to 78.5% end-to-end on the clean test and 77.5% on
the full IntAli test, below the current 85.2% / 86.6%. The loss of half the
training data hurt more than cooked-dish noise. Do not adopt the clean filter;
add clean tabletop/fridge photos instead of deleting existing images. See
`outputs/clean_filter_report.md`.

### Single-item classifier (Fruits-360 + IntAli)

A compact 100x100 Fruits-360 version (398 MB) was filtered to 30 supported
classes: 42,818 train / 4,727 val / 15,906 test images.

| Test | Model | Top-1 | Top-3 |
| --- | --- | ---: | ---: |
| Fruits-360 white background | Fruits-only | 98.9% | 99.5% |
| IntAli real-background crops | Fruits-only | 29.7% | 52.3% |
| IntAli real-background crops | + IntAli fine-tune | **94.9%** | **98.3%** |

White-background training alone does not transfer. Domain fine-tuning fixes
most of the gap, but this is a 30-class classifier; leafy greens and other
missing classes still need the detector/manual fallback. End-to-end fusion was
tested: blind replacement dropped IntAli end-to-end from 82.75% to 74.77%; a
conservative low-confidence rule reached only 83.10%. Fusion is not integrated.
See `outputs/fruits360_classifier_report.md` and `outputs/fusion_report.md`.

An agreement gate was evaluated instead: auto-submit only when detector and
classifier agree (classifier ≥0.9) gives 83.1% precision but auto-submits only
59.3% of GT; disagreements contain the right answer 98.6% of the time. This is a
precision/UX strategy, not an accuracy improvement. See
`outputs/agreement_report.md`.

## Chinese Fridge Catalog

Serving-time labels are standardized by:

```text
configs/china_fridge_catalog_v1.json
```

The catalog contains 83 common ingredients normally stored in Chinese
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
