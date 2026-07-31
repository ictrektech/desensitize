"""Reusable ONNX Runtime NER engine for optional semantic desensitization."""

import json
import logging
import os
import threading
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
        self.max_tokens = int(os.getenv("DESENSITIZE_NER_MAX_TOKENS", "512"))
        self.min_confidence = float(os.getenv("DESENSITIZE_NER_MIN_CONFIDENCE", "0.85"))
        self._semaphore = threading.BoundedSemaphore(int(os.getenv("DESENSITIZE_NER_MAX_CONCURRENCY", "1")))
        self._session = None
        self._tokenizer = None
        self._input_names: set[str] = set()
        self._label_map: dict[int, str] = {}
        self._error: str | None = None

    def startup(self) -> None:
        if not self.enabled:
            return
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
            logger.info("NER initialized once: provider=%s model=%s", self._session.get_providers()[0], self.model_dir)
        except Exception as exc:
            self._error = str(exc)
            logger.exception("NER initialization failed; regex mode remains available")

    def detect(self, text: str) -> list[dict]:
        if not self.enabled:
            raise NerUnavailable("NER is disabled")
        if self._session is None or self._tokenizer is None:
            raise NerUnavailable(self._error or "NER is unavailable")
        if not self._semaphore.acquire(blocking=False):
            raise NerUnavailable("NER is busy")
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
