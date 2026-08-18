"""
desensitize.py
==============

脱敏 API 路由。

提供:
- POST /api/v1/desensitize: 批量脱敏消息列表
- POST /api/v1/desensitize/text: 单文本脱敏
- POST /api/v1/desensitize/image: 图片脱敏
- POST /api/v1/desensitize/image/restore: 还原可逆脱敏图片
"""

import time
import logging

from fastapi import APIRouter
from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.models.schemas import (
    DesensitizeRequest,
    DesensitizeResponse,
    DesensitizeTextRequest,
    DesensitizeTextResponse,
    ImageDesensitizeRequest,
    ImageDesensitizeResponse,
    ImageRestoreRequest,
    ImageRestoreResponse,
    ReplacedItem,
    Message,
)
from app.services.engine import desensitize_text, desensitize_messages
from app.services.image_engine import desensitize_image_base64
from app.services.image_ledger import resolve_ledger_key, restore_image
from app.services.image_masker import encode_image_base64
from app.services.image_ocr import OcrUnavailable
from app.services.ner_engine import NerUnavailable

logger = logging.getLogger("ictrek-desensitize.api")

router = APIRouter(prefix="/api/v1/desensitize", tags=["desensitize"])


@router.post("", response_model=DesensitizeResponse, summary="批量脱敏消息列表")
async def desensitize(body: DesensitizeRequest):
    """
    对消息列表执行脱敏处理。

    通常在发送给云模型之前调用，将消息中的敏感信息替换为占位符。
    """
    start = time.perf_counter()

    messages = [{"role": m.role, "content": m.content} for m in body.messages]
    opts = body.options

    rule_ids = None
    if opts.rules:
        all_rules = {r["id"] for r in __import__("app.services.rule_store", fromlist=["rule_store"]).rule_store.get_all_rules()}
        rule_ids = [r for r in opts.rules if r in all_rules]

    try:
        result_messages, replaced = await run_in_threadpool(desensitize_messages, messages, rule_ids, opts.skip_roles, opts.preserve_length, opts.ner)
    except NerUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"NER requested but unavailable: {exc}") from exc

    elapsed_ms = (time.perf_counter() - start) * 1000

    return DesensitizeResponse(
        messages=[Message(**m) for m in result_messages],
        replaced=[ReplacedItem(**r) for r in replaced],
        metadata={
            "latency_ms": round(elapsed_ms, 2),
            "engine": "regex+ner" if opts.ner else "regex",
            "rule_count": len(replaced),
        },
    )


@router.post("/text", response_model=DesensitizeTextResponse, summary="单文本脱敏")
async def desensitize_text_api(body: DesensitizeTextRequest):
    """
    对单条文本执行脱敏处理。

    适用于 agent-room 等单轮场景。
    """
    start = time.perf_counter()

    rule_ids = None
    if body.rules:
        from app.services.rule_store import rule_store
        all_rule_ids = {r["id"] for r in rule_store.get_all_rules()}
        rule_ids = [r for r in body.rules if r in all_rule_ids]

    try:
        result, replaced = await run_in_threadpool(desensitize_text, body.text, rule_ids, False, body.ner)
    except NerUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"NER requested but unavailable: {exc}") from exc

    elapsed_ms = (time.perf_counter() - start) * 1000

    return DesensitizeTextResponse(
        text=result,
        replaced=[ReplacedItem(**r) for r in replaced],
        latency_ms=round(elapsed_ms, 2),
    )


@router.post("/image", response_model=ImageDesensitizeResponse, summary="图片脱敏")
async def desensitize_image_api(body: ImageDesensitizeRequest):
    """
    对图片执行 OCR + 规则脱敏，可选启用 NER。

    OCR 结果会先重建成连续文本，再执行规则匹配，避免一个敏感值被 OCR 拆成多个文本框后漏检。
    """
    rule_ids = None
    if body.rules:
        from app.services.rule_store import rule_store
        all_rule_ids = {r["id"] for r in rule_store.get_all_rules()}
        rule_ids = [r for r in body.rules if r in all_rule_ids]

    try:
        result = await run_in_threadpool(
            desensitize_image_base64,
            body.image_base64,
            mime_type=body.mime_type,
            level=body.level,
            rule_ids=rule_ids,
            ner=body.ner,
            adaptive=body.adaptive,
            reversible=body.reversible,
            ledger_key=body.ledger_key,
            return_coordinates=body.return_coordinates,
            max_side=body.max_side,
        )
    except OcrUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except NerUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"NER requested but unavailable: {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ImageDesensitizeResponse(
        image_base64=result["image_base64"],
        mime_type=result["mime_type"],
        replaced=[ReplacedItem(**r) for r in result["replaced"]],
        metadata=result["metadata"],
        latency_ms=result["latency_ms"],
        coordinates=result.get("coordinates"),
        ledger=result.get("ledger"),
    )


@router.post("/image/restore", response_model=ImageRestoreResponse, summary="还原可逆脱敏图片")
async def restore_image_api(body: ImageRestoreRequest):
    """
    用配对账本和密钥还原可逆脱敏图片中被遮挡的原始像素。

    每个遮挡区域独立解密；单个区域失败（密钥错误或数据损坏）只记录在
    report 中，不中断其余区域的还原。
    """

    def _restore() -> dict:
        key = resolve_ledger_key(body.ledger_key)
        image, report = restore_image(body.image_base64, body.ledger, key)
        return {
            "image_base64": encode_image_base64(image, body.mime_type),
            "mime_type": body.mime_type,
            "report": report,
            "restored_count": sum(1 for item in report if item.get("restored")),
        }

    try:
        result = await run_in_threadpool(_restore)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"invalid image or ledger: {exc}") from exc

    return ImageRestoreResponse(**result)
