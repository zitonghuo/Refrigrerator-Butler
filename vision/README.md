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

To keep the Git repository small, datasets and training runs are stored outside
the project:

```text
E:\fridge-keeper-datasets\
  datasets\
  runs\
```

The scripts in `scripts/` accept explicit dataset paths; pass
`--data E:\fridge-keeper-datasets\datasets\...` when evaluating or retraining.
Model weights (`weights/*.pt`) are also excluded from Git. Download the current
default from GitHub Releases (see `weights/README.md`), or keep a local copy.
The API service also needs `weights/yolov8s.pt` for the general/hybrid backend.

## Improved Model

The current serving default is the IntAli + AICook m-seg model:

```text
weights/fruits_vegetables_yolov8m_seg_aicook_v1.pt
```

It is a 47-class YOLOv8m-seg head trained on IntAli and AICook produce data.
The older 47-class v2 detector is kept as a rollback:

```text
weights/fruits_vegetables_yolov8s_cn_v2.pt
```

Weights are not tracked in Git. Download the current default from
[GitHub Releases](https://github.com/zitonghuo/Refrigrerator-Butler/releases/latest)
and verify it with the SHA256 in
[`weights/README.md`](weights/README.md).

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

The server's `--produce-weights` default points at the AICook m-seg file.

## Scope

This service only recognizes **raw produce before it is put into the fridge**.
Cooked dishes, plated meals and restaurant photos are out of scope and have
been removed from the training data and weights. Ingredient photos taken on a
table or shelf are in scope. The serving default is the 47-class IntAli + AICook
m-seg model; meat, eggs, tofu and packaged food are handled manually or by a
separate future module.

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
retains source data. The later IntAli + AICook m-seg supersedes this candidate;
see below. See `outputs/intali_report.md`.

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

### Offline augmentation (negative result)

Expanding IntAli train 3x with flip, ±12° rotation, colour/brightness and blur
gave 91.4% / 93.2% / 85.2% on IntAli, slightly below the unaugmented 91.6% /
94.6% / 86.6%. The copies add no new scenes, so they do not improve
generalization. Do not adopt; AICook or real tabletop/fridge photos are needed.
See `outputs/augmentation_report.md`.

### Automatic clean filter (negative result)

Removing prepared/processed categories left 557 train / 164 test images.
The clean-trained m-seg fell to 78.5% end-to-end on the clean test and 77.5% on
the full IntAli test, below the current 85.2% / 86.6%. The loss of half the
training data hurt more than cooked-dish noise. Do not adopt the clean filter;
add clean tabletop/fridge photos instead of deleting existing images. See
`outputs/clean_filter_report.md`.

### IntAli + AICook mixed m-seg

AICook (516 images, 30 classes, MIT) was filtered to 12 supported produce
classes and merged with IntAli masks: 1,496 train / 224 val.

| Test | Model | Recall | Class | End-to-end | FP/image |
| --- | --- | ---: | ---: | ---: | ---: |
| IntAli | IntAli-only m-seg | 91.6% | 94.6% | 86.6% | 0.48 |
| IntAli | **IntAli + AICook** | 91.1% | **94.9%** | 86.4% | **0.43** |
| AICook | IntAli-only m-seg | 22.1% | 58.3% | 12.9% | 1.53 |
| AICook | **IntAli + AICook** | **94.9%** | **97.6%** | **92.6%** | **0.31** |

AICook closes the cross-fridge gap while preserving IntAli performance. Caveat:
AICook uses one fridge/fixed camera, so 92.6% is not proof of arbitrary phone
photos. Candidate weights:
`runs/mixed_seg_v2_yolov8m/weights/best.pt`; see
`outputs/mixed_aicook_report.md`.

### 手机实拍的可选模型配置

**单品参考图模式**用于整张照片以一种食材为主的场景。在安装了 `clip-anytorch` 的 Python 环境中，为下方服务命令增加 `--single-weights <ViT-B-32.pt路径> --single-references <参考图根目录>`。参考图根目录下按食材目录中的中文名称分子文件夹，至少两类，每类放入有代表性的原图。模型与参考图在服务启动时加载一次。开发版小程序使用本机服务时，在 `app/miniprogram/config.js` 中设置 `visionUrl` 和 `singleVisionLocal: true`，再点“识别一种食材”。默认云端配置使用智谱，需部署配套的 `fridgeApi`。两种途径均允许就地选择备选名称。

在 `vision` 目录下，使用已安装本项目的 Python 环境运行：

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m food_recognition.server --backend hybrid --scene-weights weights/yolov8n-coco.pt
```

此配置需要原有的两份项目权重，以及 [Ultralytics 的 COCO YOLOv8n 权重](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt)（本地命名为 `yolov8n-coco.pt`）。苹果、香蕉、西兰花、胡萝卜和橙子使用 COCO 模型的检测结果，其余品类沿用项目模型。每帧多运行一个模型。用于本地对照测试，实际手机照片的效果和耗时需要独立验证。

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
