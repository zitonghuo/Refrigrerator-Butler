"""Private PaddleOCR service. No client-provided URLs and no image persistence."""
import asyncio
import hmac
import io
import os
from contextlib import asynccontextmanager

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from PIL import Image, ImageOps
from paddleocr import PaddleOCR

MAX_BYTES = 4 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 16_000_000
lock = asyncio.Lock()
engine = None


@asynccontextmanager
async def lifespan(app):
    global engine
    if len(os.environ.get("OCR_TOKEN", "")) < 32:
        raise RuntimeError("Set OCR_TOKEN to a random secret of at least 32 characters")
    engine = PaddleOCR(
        lang="ch",
        ocr_version="PP-OCRv5",
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


def recognize(raw):
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in {"JPEG", "PNG"} or source.width * source.height > 16_000_000:
                raise ValueError("image limits")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1920, 1920))
            pixels = np.asarray(image)[:, :, ::-1].copy()
    except Exception:
        raise HTTPException(400, "Invalid JPEG/PNG image")
    lines = []
    for result in engine.predict(pixels):
        for text, score in zip(result["rec_texts"], result["rec_scores"]):
            if float(score) >= 0.65:
                lines.append(str(text)[:200])
    return {"lines": lines[:80]}


@app.post("/recognize")
async def ocr(request: Request):
    expected = "Bearer " + os.environ["OCR_TOKEN"]
    if not hmac.compare_digest(request.headers.get("authorization", ""), expected):
        raise HTTPException(401, "Unauthorized")
    if lock.locked():
        raise HTTPException(429, "Busy, retry later")
    async with lock:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_BYTES:
                raise HTTPException(413, "Image too large")
        return await asyncio.to_thread(recognize, bytes(body))


@app.get("/health")
def health():
    return {"ready": engine is not None}
