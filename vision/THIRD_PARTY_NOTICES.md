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

## FoodInsSeg

- Project: FoodInsSeg, ingredient-level food instance segmentation
- URL: https://github.com/jamesjg/FoodInsSeg/
- Dataset page: https://laura990501.github.io/FoodInsSeg_dataset/
- License: CC BY-NC-SA 4.0 (non-commercial research only)
- Used by: `scripts/build_china_fridge_dataset.py`, merged into the local
  `china_fridge_v1` training set (7,118 images, 57 classes). Images and labels
  stay outside this repository.
- A model trained with this data must not be presented as commercially usable
  without separate permission; attribution and share-alike terms apply to
  derived dataset material.

## LVIS / COCO

- LVIS: https://www.lvisdataset.org/
- COCO: https://cocodataset.org/
- Used as the existing produce-detection training/evaluation source. Review the
  upstream image licenses and annotation terms before redistribution.

