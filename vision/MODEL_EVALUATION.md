# Food Recognition Evaluation

## Evaluation Set

The evaluation set contains 180 manually labeled images and 2,725 object
boxes from:

`datasets/fruits_vegetables_lvis_eval_v1`

It contains 63 fruit and vegetable classes. There are 121 images with multiple
objects and up to 149 objects in one image.

## Results

| Backend | Confidence | Image Size | Detection Recall | Class Accuracy on Matches | False Positives / Image |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original 90-class model | 0.25 | 640 | 3.93% | 36.45% | 0.57 |
| Original 90-class model | 0.15 | 1280 | 6.86% | 26.20% | 1.28 |
| YOLO-World + CLIP | 0.05 | 640 | 49.14% | 24.50% | 9.24 |
| YOLO-World + tiles + CLIP | 0.02 | 640 | 73.87% | 21.31% | 18.13 |
| Trained produce detector | 0.05 | 640 | 82.68% | 68.53% | 24.22 |
| Trained produce detector | 0.15 | 640 | 71.67% | 72.91% | 9.59 |
| Trained produce detector | 0.25 | 640 | 63.49% | 76.76% | 5.26 |

## Merged 71-Class Baseline (2026-10-31)

A second baseline merges FoodInsSeg (57 ingredient classes) with the LVIS
produce split, adding meat, egg, tofu, dairy and staple classes. Proper
train/val/test split; 20 epochs, 640, YOLOv8s.

| Metric | FoodInsSeg test | LVIS test | Overall |
| --- | ---: | ---: | ---: |
| Recall | 53.3% | 74.0% | 55.0% |
| Class accuracy | 80.0% | 79.1% | 79.9% |
| End-to-end | 42.6% | 58.5% | 44.0% |
| FP / image | 6.02 | 8.45 | 6.21 |

On the same 180 LVIS images, the previous 47-class produce model had 71.7%
recall / 72.9% class / 52.3% end-to-end / 9.59 FP. The merged model is better on
produce but still weak on meat and staples; see
`outputs/china_fridge_v1_test_report.md`. The serving default stays on the
47-class produce model until the 71-class catalog mapping and a real fridge test
are done.

## Chinese Household Class Pruning (2026-10-31)

The original detector had 63 classes, including foods that are rare in Chinese
households or duplicated because the upstream dataset mixed label styles. The
serving model is now:

```text
weights/fruits_vegetables_yolov8s_cn_v2.pt
```

It keeps 47 classes. Removed from the class branch:

```text
artichoke, blackberry, brussels sprouts, chickpea/garbanzo,
coconut, fig, gourd, lime, pickle, prune, raspberry, turnip,
clementine, cayenne (duplicate chili), Strawberry (duplicate),
Tomato (duplicate)
```

The original 63-class weights remain as
`weights/fruits_vegetables_yolov8s_v1.pt` for comparison. The table above was
measured on the original model; the retained classes keep their detection
behaviour, but the removed classes are no longer offered as candidates.

The blocked list is maintained in
`configs/china_household_filter_v1.json`; the same list is applied to the
free-text candidates returned by the online vision model.

## Recommended Operating Point

For user-confirmed inventory, use the trained produce detector at confidence
`0.15`:

- 71.67% object recall
- 72.91% class accuracy on matched objects
- 9.59 false positives per image

For a high-recall mode, confidence `0.05` reaches 82.68% recall, but produces
many more candidates that require user confirmation.

## Current Limits

- The trained detector covers 63 fruit and vegetable classes.
- Meat, seafood, dairy, tofu, staples, sauces, and packaged food still rely on
  the broader baseline model or future datasets.
- Dense images with tiny instances still require review.
- The system should never write predictions directly into inventory without
  user confirmation.
