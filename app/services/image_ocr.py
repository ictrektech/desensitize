"""RapidOCR wrapper with conservative concurrency for weak VOS hosts."""

from __future__ import annotations

import logging
import os
import threading
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
        self.model_dir = Path(os.getenv(
            "DESENSITIZE_IMAGE_OCR_MODEL_DIR",
            "/modelhub/export/ms/huluxiaohuowa/rapidocr-ppocrv4-onnx/current",
        ))
        self.model_id = os.getenv("DESENSITIZE_IMAGE_OCR_MODEL_ID", "huluxiaohuowa/rapidocr-ppocrv4-onnx")
        self.model_hub_url = os.getenv("MODEL_HUB_API_URL", "http://model-hub-backend:5005").rstrip("/")
        self.poll_seconds = max(2, int(os.getenv("DESENSITIZE_IMAGE_OCR_MODEL_POLL_SECONDS", "10")))
        self.max_concurrency = max(1, int(os.getenv("DESENSITIZE_IMAGE_OCR_MAX_CONCURRENCY", "1")))
        self.queue_timeout_seconds = max(0.0, float(os.getenv("DESENSITIZE_IMAGE_OCR_QUEUE_TIMEOUT_SECONDS", "20")))
        self._semaphore = threading.BoundedSemaphore(self.max_concurrency)
        self._lock = threading.Lock()
        self._ocr: Any | None = None
        self._active_providers: dict[str, list[str]] = {}
        self._error: str | None = None
        self._state = "disabled" if not self.enabled else "checking"
        self._state_lock = threading.Lock()

    def startup(self) -> None:
        if not self.enabled:
            return
        threading.Thread(target=self._ensure_model_then_initialize, name="desensitize-image-ocr-modelhub", daemon=True).start()

    def detect(self, image: Image.Image) -> list[OcrBlock]:
        if not self.enabled:
            raise OcrUnavailable("image OCR is disabled")
        if self._ocr is None:
            if self._missing_model_files():
                raise OcrUnavailable("图片 OCR 模型下载中，请稍后")
            if self._state in {"checking", "downloading"}:
                raise OcrUnavailable("图片 OCR 模型下载中，请稍后")
            raise OcrUnavailable(self._error or "image OCR unavailable")
        if not self._semaphore.acquire(timeout=self.queue_timeout_seconds):
            raise OcrUnavailable("图片 OCR 队列繁忙，请稍后")
        try:
            array = np.array(image.convert("RGB"))
            result = self._ocr(array)
            return _parse_rapidocr_result(result)
        finally:
            self._semaphore.release()

    def info(self) -> dict:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "active_providers": self._active_providers,
            "state": self._state,
            "model_id": self.model_id,
            "model_dir": str(self.model_dir),
            "max_concurrency": self.max_concurrency,
            "queue_timeout_seconds": self.queue_timeout_seconds,
            "ready": self._ocr is not None,
            "error": self._error,
        }

    def _set_state(self, state: str, error: str | None = None) -> None:
        with self._state_lock:
            self._state = state
            self._error = error

    def _model_hub_json(self, path: str, method: str = "GET", payload: dict | None = None) -> object:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.model_hub_url}{path}", body, method=method,
            headers={"Content-Type": "application/json"} if body else {},
        )
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

    def _model_status(self) -> str | None:
        models = self._model_hub_json("/api/v1/models?status=all")
        if not isinstance(models, list):
            raise OcrUnavailable("Model Hub returned an invalid model list")
        for model in models:
            if isinstance(model, dict) and model.get("model_id") == self.model_id:
                return str(model.get("status", ""))
        return None

    def _request_model_pull(self) -> None:
        try:
            self._model_hub_json(
                "/api/v1/models/pull", "POST",
                {"model_id": self.model_id, "source": "ms", "name": "rapidocr-ppocrv4-onnx"},
            )
            logger.info("RapidOCR model pull requested from Model Hub: %s", self.model_id)
        except HTTPError as exc:
            if exc.code != 409:
                raise

    def _model_files(self) -> tuple[Path, Path, Path]:
        return (
            self.model_dir / "ch_PP-OCRv4_det_infer.onnx",
            self.model_dir / "ch_PP-OCRv4_rec_infer.onnx",
            self.model_dir / "ch_ppocr_mobile_v2.0_cls_infer.onnx",
        )

    def _missing_model_files(self) -> list[str]:
        return [str(path) for path in self._model_files() if not path.is_file()]

    def _ensure_model_then_initialize(self) -> None:
        pull_requested = False
        while True:
            try:
                if not self._missing_model_files():
                    self._initialize_ocr()
                    return
                status = self._model_status()
                if status == "ready":
                    self._initialize_ocr()
                    return
                if status in {None, "failed"} and not pull_requested:
                    self._request_model_pull()
                    pull_requested = True
                self._set_state("downloading")
                logger.info("RapidOCR model is %s; retrying Model Hub in %ss", status or "not present", self.poll_seconds)
            except (HTTPError, URLError, TimeoutError, ValueError, OcrUnavailable) as exc:
                self._set_state("unavailable", f"Model Hub unavailable: {exc}")
                logger.warning("RapidOCR Model Hub check failed; retrying in %ss: %s", self.poll_seconds, exc)
            except Exception as exc:
                self._set_state("unavailable", str(exc))
                logger.exception("Unexpected RapidOCR Model Hub check failure")
            time.sleep(self.poll_seconds)

    def _initialize_ocr(self) -> Any:
        with self._lock:
            if self._ocr is not None:
                return self._ocr
            try:
                from rapidocr_onnxruntime import RapidOCR

                det_model, rec_model, cls_model = self._model_files()
                missing = self._missing_model_files()
                if missing:
                    raise OcrUnavailable("Model Hub OCR model is missing: " + ", ".join(missing))

                self._ocr = RapidOCR(
                    det_model_path=str(det_model),
                    rec_model_path=str(rec_model),
                    cls_model_path=str(cls_model),
                    **_rapidocr_provider_kwargs(self.provider),
                )
                self._active_providers = _rapidocr_active_providers(self._ocr)
                if self.provider == "cuda" and not _rapidocr_uses_cuda(self._active_providers):
                    raise OcrUnavailable(f"CUDAExecutionProvider is unavailable for RapidOCR: {self._active_providers}")
                self._error = None
                self._set_state("ready")
                logger.info("RapidOCR initialized: provider=%s active=%s model=%s", self.provider, self._active_providers, self.model_dir)
                return self._ocr
            except Exception as exc:
                self._set_state("unavailable", str(exc))
                logger.exception("RapidOCR initialization failed")
                raise OcrUnavailable(f"image OCR unavailable: {exc}") from exc


def _rapidocr_provider_kwargs(provider: str) -> dict[str, bool]:
    if provider == "cuda":
        return {"det_use_cuda": True, "rec_use_cuda": True, "cls_use_cuda": True}
    if provider == "cpu":
        return {"det_use_cuda": False, "rec_use_cuda": False, "cls_use_cuda": False}
    return {}


def _rapidocr_active_providers(ocr: Any) -> dict[str, list[str]]:
    providers: dict[str, list[str]] = {}
    targets = {
        "det": (getattr(getattr(ocr, "text_det", None), "infer", None)),
        "cls": (getattr(getattr(ocr, "text_cls", None), "infer", None)),
        "rec": (getattr(getattr(ocr, "text_rec", None), "session", None)),
    }
    for name, infer in targets.items():
        session = getattr(infer, "session", None)
        if session is not None and hasattr(session, "get_providers"):
            providers[name] = list(session.get_providers())
    return providers


def _rapidocr_uses_cuda(active_providers: dict[str, list[str]]) -> bool:
    if not active_providers:
        return False
    return all(providers and providers[0] == "CUDAExecutionProvider" for providers in active_providers.values())


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
