# Third-party components

## PaddleOCR / PaddlePaddle

- Source: https://github.com/PaddlePaddle/PaddleOCR
- Runtime dependency: paddleocr 3.2.0; paddlepaddle 3.2.0
- License: Apache License 2.0
- License text: https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE
- Used by the separately deployed `ocr-service` for packaging text recognition.
- Models: PP-OCRv5_mobile_det and PP-OCRv5_mobile_rec, downloaded by the official runtime. Preserve the upstream license/notices and verify model artifact terms and hashes when building the production image.
- This repository contains integration code, not a copied PaddleOCR source distribution.

## Other runtime dependencies

The OCR service additionally uses FastAPI (MIT), Uvicorn (BSD-3-Clause), Pillow (HPND), and transitive dependencies. Retain installed license files in the container and generate an SBOM for the built image before release.

## Design reference only

https://github.com/prathmachowksey/Smart-Refrigerator-Management-System

Referenced its published inventory/category/expiry management feature description. No code or assets copied; no license was confirmed for reuse.

Camera, video selection and playback use WeChat's platform APIs rather than a third-party camera library.
