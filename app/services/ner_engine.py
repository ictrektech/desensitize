"""Reusable ONNX Runtime NER engine for optional semantic desensitization."""

import json
import logging
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from pathlib import Path

logger = logging.getLogger("ictrek-desensitize.ner")


class NerUnavailable(RuntimeError):
    pass


class NerEngine:
    def __init__(self) -> None:
        self.enabled = os.getenv("DESENSITIZE_NER_ENABLED", "true").lower() == "true"
        self.model_dir = Path(os.getenv(
            "DESENSITIZE_NER_MODEL_DIR",
            "/modelhub/export/ms/huluxiaohuowa/bert4ner-base-chinese-onnx/current",
        ))
        self.provider = os.getenv("DESENSITIZE_NER_PROVIDER", "auto").lower()
        self.model_hub_url = os.getenv("MODEL_HUB_API_URL", "http://model-hub-backend:5005").rstrip("/")
        self.model_id = os.getenv("DESENSITIZE_NER_MODEL_ID", "huluxiaohuowa/bert4ner-base-chinese-onnx")
        self.poll_seconds = max(2, int(os.getenv("DESENSITIZE_NER_MODEL_POLL_SECONDS", "10")))
        self.max_tokens = int(os.getenv("DESENSITIZE_NER_MAX_TOKENS", "512"))
        self.min_confidence = float(os.getenv("DESENSITIZE_NER_MIN_CONFIDENCE", "0.85"))
        self.max_concurrency = max(1, int(os.getenv("DESENSITIZE_NER_MAX_CONCURRENCY", "4")))
        self.queue_timeout_seconds = max(0, float(os.getenv("DESENSITIZE_NER_QUEUE_TIMEOUT_SECONDS", "30")))
        self._semaphore = threading.BoundedSemaphore(self.max_concurrency)
        self._session = None
        self._tokenizer = None
        self._input_names: set[str] = set()
        self._label_map: dict[int, str] = {}
        self._error: str | None = None
        self._state = "disabled" if not self.enabled else "checking"
        self._state_lock = threading.Lock()

    def startup(self) -> None:
        if not self.enabled:
            return
        threading.Thread(target=self._ensure_model_then_initialize, name="desensitize-ner-modelhub", daemon=True).start()

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
            raise NerUnavailable("Model Hub returned an invalid model list")
        for model in models:
            if isinstance(model, dict) and model.get("model_id") == self.model_id:
                return str(model.get("status", ""))
        return None

    def _request_model_pull(self) -> None:
        try:
            self._model_hub_json(
                "/api/v1/models/pull", "POST",
                {"model_id": self.model_id, "source": "ms", "name": "bert4ner-base-chinese-onnx"},
            )
            logger.info("NER model pull requested from Model Hub: %s", self.model_id)
        except HTTPError as exc:
            if exc.code != 409:
                raise

    def _ensure_model_then_initialize(self) -> None:
        """Never block FastAPI startup on Model Hub download or ONNX initialization."""
        pull_requested = False
        while True:
            try:
                status = self._model_status()
                if status == "ready":
                    self._initialize_session()
                    return
                if status in {None, "failed"} and not pull_requested:
                    self._request_model_pull()
                    pull_requested = True
                self._set_state("downloading")
                logger.info("NER model is %s; retrying Model Hub in %ss", status or "not present", self.poll_seconds)
            except (HTTPError, URLError, TimeoutError, ValueError, NerUnavailable) as exc:
                self._set_state("unavailable", f"Model Hub unavailable: {exc}")
                logger.warning("NER Model Hub check failed; retrying in %ss: %s", self.poll_seconds, exc)
            except Exception as exc:
                self._set_state("unavailable", str(exc))
                logger.exception("Unexpected NER Model Hub check failure")
            time.sleep(self.poll_seconds)

    def _initialize_session(self) -> None:
        try:
            import onnxruntime as ort
            from transformers import AutoTokenizer

            if not (self.model_dir / "model.onnx").is_file():
                raise NerUnavailable(
                    f"Model Hub model is missing: {self.model_dir}/model.onnx. "
                    "Install huluxiaohuowa/bert4ner-base-chinese-onnx in Model Hub first."
                )
            providers = ["CPUExecutionProvider"]
            if self.provider in {"auto", "cuda"} and "CUDAExecutionProvider" in ort.get_available_providers():
                providers.insert(0, "CUDAExecutionProvider")
            if self.provider == "cuda" and providers[0] != "CUDAExecutionProvider":
                raise NerUnavailable("CUDAExecutionProvider is unavailable")
            options = ort.SessionOptions()
            options.intra_op_num_threads = int(os.getenv("DESENSITIZE_NER_INTRA_OP_THREADS", "4"))
            options.inter_op_num_threads = 1
            self._tokenizer = AutoTokenizer.from_pretrained(self.model_dir, local_files_only=True, use_fast=True)
            self._session = ort.InferenceSession(str(self.model_dir / "model.onnx"), sess_options=options, providers=providers)
            self._input_names = {item.name for item in self._session.get_inputs()}
            config = json.loads((self.model_dir / "config.json").read_text(encoding="utf-8"))
            self._label_map = {int(key): value for key, value in config["id2label"].items()}
            self._set_state("ready")
            logger.info("NER initialized once: provider=%s model=%s", self._session.get_providers()[0], self.model_dir)
        except Exception as exc:
            self._set_state("unavailable", str(exc))
            logger.exception("NER initialization failed; regex mode remains available")

    def detect(self, text: str) -> list[dict]:
        if not self.enabled:
            raise NerUnavailable("NER is disabled")
        if self._session is None or self._tokenizer is None:
            if self._state in {"checking", "downloading"}:
                raise NerUnavailable("模型下载中，请稍后")
            raise NerUnavailable(self._error or "NER is unavailable")
        if not self._semaphore.acquire(timeout=self.queue_timeout_seconds):
            raise NerUnavailable("NER 队列繁忙，请稍后")
        try:
            import numpy as np
            encoded = self._tokenizer(text, return_offsets_mapping=True, truncation=True, max_length=self.max_tokens, return_tensors="np")
            offsets = encoded.pop("offset_mapping")[0]
            logits = self._session.run(None, {k: v for k, v in encoded.items() if k in self._input_names})[0][0]
            logits -= logits.max(axis=-1, keepdims=True)
            probs = np.exp(logits) / np.exp(logits).sum(axis=-1, keepdims=True)
            labels = probs.argmax(axis=-1)
            entities: list[dict] = []
            current = None
            for index, (start, end) in enumerate(offsets):
                label = self._label_map.get(int(labels[index]), "O")
                confidence = float(probs[index, labels[index]])
                kind = label[2:] if label.startswith(("B-", "I-")) else ""
                if start == end or kind not in {"PER", "LOC"} or confidence < self.min_confidence:
                    if current: entities.append(current); current = None
                    continue
                if label.startswith("B-") or not current or current["kind"] != kind or start > current["end"]:
                    if current: entities.append(current)
                    current = {"kind": kind, "start": int(start), "end": int(end), "confidence": confidence}
                else:
                    current["end"] = int(end); current["confidence"] = min(current["confidence"], confidence)
            if current: entities.append(current)
            return entities
        finally:
            self._semaphore.release()


ner_engine = NerEngine()
