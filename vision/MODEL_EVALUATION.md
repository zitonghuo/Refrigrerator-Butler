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
