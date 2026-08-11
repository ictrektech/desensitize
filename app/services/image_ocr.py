"""RapidOCR wrapper with conservative concurrency for weak VOS hosts."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any

import numpy as np
from PIL import Image

from app.services.image_layout import OcrBlock, Point, rect_from_quad

logger = logging.getLogger("ictrek-desensitize.image_ocr")


class OcrUnavailable(RuntimeError):
    pass


class RapidOcrEngine:
    def __init__(self) -> None:
        self.enabled = os.getenv("DESENSITIZE_IMAGE_OCR_ENABLED", "true").lower() == "true"
        self.provider = os.getenv("DESENSITIZE_IMAGE_OCR_PROVIDER", os.getenv("DESENSITIZE_NER_PROVIDER", "auto")).lower()
        self.max_concurrency = max(1, int(os.getenv("DESENSITIZE_IMAGE_OCR_MAX_CONCURRENCY", "1")))
        self.queue_timeout_seconds = max(0.0, float(os.getenv("DESENSITIZE_IMAGE_OCR_QUEUE_TIMEOUT_SECONDS", "20")))
        self._semaphore = threading.BoundedSemaphore(self.max_concurrency)
        self._lock = threading.Lock()
        self._ocr: Any | None = None
        self._error: str | None = None

    def detect(self, image: Image.Image) -> list[OcrBlock]:
        if not self.enabled:
            raise OcrUnavailable("image OCR is disabled")
        if not self._semaphore.acquire(timeout=self.queue_timeout_seconds):
            raise OcrUnavailable("图片 OCR 队列繁忙，请稍后")
        try:
            ocr = self._get_ocr()
            array = np.array(image.convert("RGB"))
            result = ocr(array)
            return _parse_rapidocr_result(result)
        finally:
            self._semaphore.release()

    def info(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "max_concurrency": self.max_concurrency,
            "queue_timeout_seconds": self.queue_timeout_seconds,
            "ready": self._ocr is not None,
            "error": self._error,
        }

    def _get_ocr(self) -> Any:
        if self._ocr is not None:
            return self._ocr
        with self._lock:
            if self._ocr is not None:
                return self._ocr
            try:
                from rapidocr_onnxruntime import RapidOCR

                providers = _providers_for(self.provider)
                try:
                    self._ocr = RapidOCR(providers=providers)
                except TypeError:
                    # Older rapidocr_onnxruntime versions do not accept providers.
                    self._ocr = RapidOCR()
                self._error = None
                logger.info("RapidOCR initialized: provider=%s", self.provider)
                return self._ocr
            except Exception as exc:
                self._error = str(exc)
                logger.exception("RapidOCR initialization failed")
                raise OcrUnavailable(f"image OCR unavailable: {exc}") from exc


def _providers_for(provider: str) -> list[str] | None:
    if provider == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if provider == "cpu":
        return ["CPUExecutionProvider"]
    return None


def _parse_rapidocr_result(result: Any) -> list[OcrBlock]:
    # rapidocr_onnxruntime normally returns (results, elapsed), where each item is
    # [box, text, score]. Keep this parser tolerant for version differences.
    items = result[0] if isinstance(result, tuple) else result
    if items is None:
        return []

    blocks: list[OcrBlock] = []
    for item in items:
        try:
            box, text, score = item[0], item[1], float(item[2]) if len(item) > 2 else 1.0
            quad = [Point(float(p[0]), float(p[1])) for p in box]
            bbox = rect_from_quad(quad)
            blocks.append(OcrBlock(text=str(text), quad=quad, bbox=bbox, score=score))
        except Exception:
            logger.warning("Skipping unrecognized OCR item: %r", item)
    return blocks


image_ocr_engine = RapidOcrEngine()
