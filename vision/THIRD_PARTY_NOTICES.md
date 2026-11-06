# Third-Party Notices

## food-recognition

The code under `vendor/upstream` is copied from:

- Project: `lannguyen0910/food-recognition`
- URL: https://github.com/lannguyen0910/food-recognition
- Retrieved: 2026-09-29
- License: MIT

The upstream license is retained at `vendor/upstream/LICENSE`.

The pretrained model weights are hosted separately by the upstream project and
are not included in this directory. Their data and distribution terms must be
reviewed independently before production use.

The files under `samples/` are upstream demo uploads retained only for local
smoke testing.

## IntAli Food Dataset

- Project: https://aimas.cs.pub.ro/intali/
- Kaggle: https://www.kaggle.com/datasets/miketrs/intali-food-dataset
- License: CC BY-NC-SA 4.0 (non-commercial)
- Used for a raw-produce fine-tuning/evaluation subset (26 mapped classes,
  1,130 train / 125 val / 382 test images). Images stay outside this repository.
- Attribution and share-alike terms apply to derived material; do not use this
  model commercially without checking the dataset licence.

## AICook

- Dataset: https://universe.roboflow.com/karel-cornelis-q2qqg/aicook-lcv4d/dataset/1
- License: MIT
- Used for 12 supported produce classes, 362 train / 103 valid / 51 test images.
  Images stay outside this repository.

## LVIS / COCO

- LVIS: https://www.lvisdataset.org/
- COCO: https://cocodataset.org/
- Used as the existing produce-detection training/evaluation source. Review the
  upstream image licenses and annotation terms before redistribution.

