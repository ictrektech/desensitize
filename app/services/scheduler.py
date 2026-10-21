from __future__ import annotations

import asyncio
import contextvars
import ctypes
import json
import math
from importlib import metadata
import os
import secrets
import threading
from contextlib import contextmanager
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Request


APP_ID = "com.ictrek.desensitize"
PREFIX = "DESENSITIZE"
UPSTREAM = "http://desensitize-backend:5000/v1"
URL = "http://v-router:8080/scheduler/api/v1"
router = APIRouter(prefix="/api/v1/scheduler")
headers_context = contextvars.ContextVar("scheduler_headers", default={})
lock = threading.RLock()
execution_lock = threading.Lock()
active = 0


def release_unused_host_memory():
    # ONNX sessions are gone, but glibc may retain their freed CPU heap pages.
    # This is best effort; it is not evidence that GPU execution has stopped.
    try:
        trim = ctypes.CDLL(None).malloc_trim
        trim.argtypes = [ctypes.c_size_t]
        trim.restype = ctypes.c_int
        trim(0)
    except (AttributeError, OSError):
        pass


def execution_settings():
    from .ner_engine import ner_engine
    from .image_ocr import image_ocr_engine
    try:
        import onnxruntime
        providers = sorted(onnxruntime.get_available_providers())
        ort_version = onnxruntime.__version__
    except ImportError:
        providers, ort_version = [], "unavailable"
    try:
        ocr_version = metadata.version("rapidocr-onnxruntime")
    except metadata.PackageNotFoundError:
        ocr_version = "unavailable"
    return {"ner_provider_requested": ner_engine.provider, "ocr_provider_requested": image_ocr_engine.provider, "onnx_available_providers": providers, "onnxruntime_version": ort_version, "rapidocr_version": ocr_version, "logical_cpu_count": os.cpu_count(), "ner_intra_op_threads": int(os.getenv("DESENSITIZE_NER_INTRA_OP_THREADS", "4")), "ner_inter_op_threads": 1, "ocr_thread_policy": "fixed-1", "ocr_intra_op_threads": 1, "ocr_inter_op_threads": 1, "opencv_threads": 1, "math_thread_environment": {name: os.getenv(name, "unset") for name in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"]}, "max_concurrent_inference": 1, "ner_max_tokens": ner_engine.max_tokens}


def validate_limits(model, inputs, config=None):
    if not required():
        return
    config = config or read_config()
    limits = config.get("model_limits", {}).get(model, {})
    for field, value in inputs.items():
        maximum = limits.get(field)
        if type(maximum) not in {int, float} or not math.isfinite(maximum) or maximum < 0:
            raise HTTPException(503, "Calibrated input limit required: " + field)
        if type(value) not in {int, float} or not math.isfinite(value) or value > maximum or value < 0:
            raise HTTPException(422, "Input exceeds calibrated limit: " + field)


def required():
    return os.getenv(PREFIX + "_SCHEDULER_REQUIRED") == "true"


def config_path():
    return Path(os.getenv(PREFIX + "_SCHEDULER_CONFIG", "/data/scheduler.local.json"))


def read_config(*, current_settings=True):
    path = config_path()
    try:
        info = path.lstat()
        if path.is_symlink() or not path.is_file() or info.st_mode & 0o077 or info.st_size > 262144:
            raise ValueError("private configuration required")
        value = json.loads(path.read_text())
        if value.get("url") != URL or value.get("app_id") != APP_ID or value.get("upstream_url") != UPSTREAM:
            raise ValueError("invalid service binding")
        if len(value.get("token", "")) < 32:
            raise ValueError("missing service identity")
        if current_settings and value.get("execution_settings") != execution_settings():
            raise ValueError("runtime settings no longer match approval")
        return value
    except (OSError, ValueError, TypeError, AttributeError):
        raise HTTPException(503, "V-Scheduler binding required") from None


def controller(config, method, path, body=None, key=""):
    headers = {"Authorization": "Bearer " + config["token"]}
    from .scheduling_options import operator_headers
    headers.update(operator_headers((body or {}).get("scheduling", {}), headers_context.get().get("authorization", "")))
    if key:
        headers["Idempotency-Key"] = key
    try:
        response = httpx.request(method, URL + path, headers=headers, json=body, timeout=8, follow_redirects=False)
        if response.status_code == 429:
            raise HTTPException(429, "Compute resources busy", headers={"Retry-After": "1"})
        response.raise_for_status()
        value = response.json()
        if value.get("code") != "OK":
            raise ValueError("invalid scheduler response")
        return value["data"]
    except (httpx.HTTPError, ValueError, KeyError):
        raise HTTPException(503, "V-Scheduler unavailable") from None


class SchedulerHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = headers_context.set({key.decode().lower(): value.decode() for key, value in scope.get("headers", [])})
        try:
            await self.app(scope, receive, send)
        finally:
            headers_context.reset(token)


@router.get("/binding")
def binding_status():
    try:
        config = read_config()
    except HTTPException:
        return {"protocol_version": 1, "configured": False}
    return {"protocol_version": 1, "configured": True, "binding_revision": config.get("binding_revision"), "approved_model_count": len(config.get("models", {}))}


@router.post("/binding")
async def bind(request: Request):
    identity_url = os.getenv("VOS_USERINFO_URL")
    if not identity_url:
        port = os.getenv("VOS_API_GW_PORT_INTERNAL", "")
        if not port.isdigit():
            raise HTTPException(503, "VOS identity service unavailable")
        identity_url = "http://host.docker.internal:" + port + "/v1000/oauth2/userinfo"
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=False) as client:
            identity = await client.get(identity_url, headers={"Authorization": request.headers.get("authorization", "")})
            if identity.status_code == 401 and identity.json().get("error") == "invalid_token":
                from urllib.parse import urlsplit, urlunsplit
                endpoint = urlsplit(identity_url)
                checked = await client.get(urlunsplit((endpoint.scheme, endpoint.netloc, "/v1000/user/check", "", "")), headers={"Authorization": request.headers.get("authorization", "")})
                checked.raise_for_status()
                envelope = checked.json()
                verified = envelope.get("data", {})
                if not (envelope.get("code") == 0 and verified.get("username") == "com.ictrek.v-scheduler" and verified.get("role_code") == "system_admin" and verified.get("enable") == 1 and verified.get("delete") == 0 and verified.get("id")):
                    raise HTTPException(403, "V-Scheduler application identity required")
                user = {"sub": verified["username"], "enable": verified["enable"]}
            else:
                identity.raise_for_status()
                user = identity.json()
    except (httpx.HTTPError, ValueError):
        raise HTTPException(401, "VOS application identity required") from None
    if not isinstance(user, dict) or user.get("sub") != "com.ictrek.v-scheduler" or user.get("enable") != 1:
        raise HTTPException(403, "V-Scheduler application identity required")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > 262144:
            raise HTTPException(413, "Binding too large")
    try:
        config = json.loads(body)
        if config.get("protocol_version") != 1 or type(config.get("binding_revision")) is not int or config["binding_revision"] < 1:
            raise ValueError()
        if config.get("app_id") != APP_ID or config.get("url") != URL or config.get("upstream_url") != UPSTREAM:
            raise ValueError()
        for field in ("token", "executor_token"):
            if not isinstance(config.get(field), str) or not 32 <= len(config[field]) <= 4096 or any(character.isspace() for character in config[field]):
                raise ValueError()
        if not isinstance(config.get("models"), dict) or not 1 <= len(config["models"]) <= 512:
            raise ValueError()
        if config.get("execution_settings") != execution_settings() or not isinstance(config.get("model_limits"), dict):
            raise ValueError()
        for field in ("models", "gateway_executors"):
            mapping = config.get(field, {})
            if not isinstance(mapping, dict) or len(mapping) > 512 or any(not isinstance(model, str) or not isinstance(executor, str) or not model or not executor for model, executor in mapping.items()):
                raise ValueError()
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(422, "Invalid application binding") from None
    executors = await asyncio.to_thread(controller, config, "GET", "/executors")
    approved = {row["id"] for row in executors if row.get("app_id") == APP_ID and row.get("task_type") == "model.infer" and row.get("contract_version") == "1" and UPSTREAM in row.get("upstream_urls", [])}
    if any(executor not in approved for executor in config["models"].values()):
        raise HTTPException(422, "Executor not approved for this application")
    with lock:
        if active:
            raise HTTPException(409, "Binding waits for active execution")
        path = config_path()
        if path.exists():
            # An authenticated newer approval may replace an obsolete runtime binding.
            # Compute paths still require the saved settings to match the runtime.
            previous = read_config(current_settings=False)
            if previous.get("binding_revision", 0) >= config["binding_revision"]:
                if previous == config:
                    return {"configured": True, "binding_revision": config["binding_revision"]}
                raise HTTPException(409, "Binding revision conflict")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
        with open(temporary, "x", opener=lambda filename, flags: os.open(filename, flags, 0o600)) as stream:
            json.dump(config, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    return {"configured": True, "binding_revision": config["binding_revision"]}


_lifecycle = None

def lifecycle():
    global _lifecycle
    if _lifecycle is None:
        from .scheduler_lifecycle import Lifecycle
        _lifecycle = Lifecycle(read_config, config_path().with_name("scheduler.lifecycle.json"))
    return _lifecycle


def lifecycle_call(method, *args):
    from .scheduler_lifecycle import LifecycleError
    try:
        return getattr(lifecycle(), method)(*args)
    except (LifecycleError, OSError):
        raise HTTPException(503, "Application lifecycle unavailable") from None


@contextmanager
def compute(model, unload, inputs=None):
    if not required():
        yield
        return
    with execution_lock:
        with _compute(model, unload, inputs):
            yield


@contextmanager
def _compute(model, unload, inputs=None):
    global active
    if not required():
        yield
        return
    with lock:
        config = read_config()
        validate_limits(model, inputs or {}, config)
        if config.get('lifecycle_protocol_version') == 1:
            lifecycle_call("ensure", config)
        active += 1
    permit = ""
    owned = False
    stop = threading.Event()
    failed = threading.Event()
    execution = secrets.token_hex(16)
    incoming = headers_context.get()
    executor = config.get("models", {}).get(model, "")
    proof = secrets.token_hex(32)
    try:
        if incoming.get("x-vscheduler-permit-id") or incoming.get("x-vscheduler-execution-token") or incoming.get("x-vscheduler-executor-id"):
            permit = incoming.get("x-vscheduler-permit-id", "")
            proof = incoming.get("x-vscheduler-execution-token", "")
            executor = incoming.get("x-vscheduler-executor-id", "")
            if not permit or len(proof) < 32 or not executor or executor != config.get("gateway_executors", {}).get(model):
                raise HTTPException(503, "Invalid gateway admission proof")
        else:
            if not executor:
                raise HTTPException(503, "Model executor is not approved")
            from .scheduling_options import options_from_headers
            options = options_from_headers(incoming)
            value = controller(config, "POST", "/permits", {"executor_id": executor, "model_id": model, "upstream_url": UPSTREAM, "execution_token": proof, **({"scheduling": options} if options else {})}, execution)
            permit = value.get("permit_id", "")
            owned = True
        if not permit:
            raise HTTPException(503, "Missing admission receipt")

        def verify(claim=False):
            value = controller(config, "POST", "/permits/" + permit + "/verify", {"executor_id": executor, "model_id": model, "upstream_url": UPSTREAM, "execution_token": proof, "execution_id": execution, "claim": claim})
            if value.get("state") != "active" or value.get("lease_seconds", 0) < 1:
                raise HTTPException(503, "Compute lease expired")

        if config.get('lifecycle_protocol_version') == 1:
            lifecycle_call("attach", config, permit, execution, proof, failed.set)
        verify(True)
        if config.get('lifecycle_protocol_version') == 1:
            lifecycle_call("claimed", permit, execution)

        def watch():
            while not stop.wait(5):
                try:
                    if owned:
                        controller(config, "POST", "/permits/" + permit + "/renew", {})
                    verify()
                except HTTPException:
                    failed.set()
                    return

        threading.Thread(target=watch, daemon=True).start()
        yield
        if failed.is_set():
            raise HTTPException(503, "Compute lease was lost")
    finally:
        stop.set()
        stopped = False
        try:
            unload()
            release_unused_host_memory()
            stopped = True
            if permit and config.get('lifecycle_protocol_version') == 1:
                lifecycle_call("finished", permit, True)
        finally:
            if owned and permit:
                try:
                    controller(config, "POST", "/permits/" + permit + "/release", {"stopped": stopped, "evidence": "application_call_completed_and_model_unloaded" if stopped else "model_unload_not_confirmed"})
                    if stopped and config.get('lifecycle_protocol_version') == 1:
                        lifecycle_call("released", permit)
                except HTTPException:
                    pass
            with lock:
                active -= 1
