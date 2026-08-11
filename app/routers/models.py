"""Desensitize model management proxy for Model Hub."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException

from app.services.image_ocr import image_ocr_engine
from app.services.ner_engine import ner_engine

router = APIRouter(prefix="/api/v1/models", tags=["models"])


MODEL_HUB_URL = os.getenv("MODEL_HUB_API_URL", "http://model-hub-backend:5005").rstrip("/")

MANAGED_MODELS = {
    "ner": {
        "key": "ner",
        "name": "NER 人名/地址模型",
        "description": "用于 ner=true 时补充识别人名和地址。",
        "model_id": ner_engine.model_id,
        "source": "ms",
        "pull_name": "bert4ner-base-chinese-onnx",
        "model_dir": str(ner_engine.model_dir),
    },
    "ocr": {
        "key": "ocr",
        "name": "图片 OCR 模型",
        "description": "用于图片脱敏接口识别图片中的文本框。",
        "model_id": image_ocr_engine.model_id,
        "source": "ms",
        "pull_name": "rapidocr-ppocrv4-onnx",
        "model_dir": str(image_ocr_engine.model_dir),
    },
}


def _model_hub_json(path: str, method: str = "GET", payload: dict | None = None) -> Any:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(
        f"{MODEL_HUB_URL}{path}",
        body,
        method=method,
        headers={"Content-Type": "application/json"} if body else {},
    )
    try:
        with urlopen(request, timeout=10) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace") or str(exc)
        raise HTTPException(status_code=exc.code, detail=detail) from exc
    except (URLError, TimeoutError) as exc:
        raise HTTPException(status_code=503, detail=f"Model Hub unavailable: {exc}") from exc


def _find_model(models: list[dict], model_id: str) -> dict | None:
    for model in models:
        if isinstance(model, dict) and model.get("model_id") == model_id:
            return model
    return None


def _find_task(tasks: list[dict], model_id: str) -> dict | None:
    candidates = [task for task in tasks if isinstance(task, dict) and task.get("model_id") == model_id]
    if not candidates:
        return None
    phase_order = {"PENDING": 0, "DOWNLOADING": 1, "VERIFYING": 2, "READY": 3, "FAILED": 4}
    return sorted(candidates, key=lambda item: phase_order.get(str(item.get("phase")), 9))[0]


def _runtime_info(key: str) -> dict:
    if key == "ner":
        return ner_engine.info()
    return image_ocr_engine.info()


def _managed_model_status(key: str, models: list[dict] | None = None, tasks: list[dict] | None = None) -> dict:
    spec = MANAGED_MODELS[key]
    models = models if models is not None else _model_hub_json("/api/v1/models?status=all")
    tasks = tasks if tasks is not None else _model_hub_json("/api/v1/tasks")
    if not isinstance(models, list):
        models = []
    if not isinstance(tasks, list):
        tasks = []
    model = _find_model(models, spec["model_id"])
    task = _find_task(tasks, spec["model_id"])
    runtime = _runtime_info(key)
    status = str(model.get("status")) if model else "missing"
    if task and str(task.get("phase")) not in {"READY", "FAILED"}:
        status = "pulling"
    return {
        **spec,
        "status": status,
        "ready": status == "ready" or runtime.get("state") == "ready",
        "runtime": runtime,
        "model": model,
        "task": task,
    }


@router.get("/managed", summary="列出脱敏服务依赖的模型")
async def list_managed_models():
    models = _model_hub_json("/api/v1/models?status=all")
    tasks = _model_hub_json("/api/v1/tasks")
    return [_managed_model_status(key, models, tasks) for key in ("ner", "ocr")]


@router.post("/managed/{key}/download", summary="触发模型下载")
async def download_managed_model(key: str):
    if key not in MANAGED_MODELS:
        raise HTTPException(status_code=404, detail=f"unknown model key: {key}")
    spec = MANAGED_MODELS[key]
    try:
        result = _model_hub_json(
            "/api/v1/models/pull",
            "POST",
            {"model_id": spec["model_id"], "source": spec["source"], "name": spec["pull_name"]},
        )
    except HTTPException as exc:
        if exc.status_code != 409:
            raise
        result = {"message": "model is already present or downloading"}
    return {"model": _managed_model_status(key), "result": result}


@router.post("/managed/{key}/check-update", summary="检查模型版本更新")
async def check_managed_model_update(key: str):
    if key not in MANAGED_MODELS:
        raise HTTPException(status_code=404, detail=f"unknown model key: {key}")
    model_id = quote(MANAGED_MODELS[key]["model_id"], safe="")
    result = _model_hub_json(f"/api/v1/models/check-update?model_id={model_id}", "POST")
    return {"model": _managed_model_status(key), "result": result}


@router.post("/managed/{key}/update", summary="更新模型")
async def update_managed_model(key: str):
    if key not in MANAGED_MODELS:
        raise HTTPException(status_code=404, detail=f"unknown model key: {key}")
    model_id = quote(MANAGED_MODELS[key]["model_id"], safe="")
    result = _model_hub_json(f"/api/v1/models/update?model_id={model_id}", "POST")
    return {"model": _managed_model_status(key), "result": result}
