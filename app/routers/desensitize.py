"""
desensitize.py
==============

脱敏 API 路由。

提供:
- POST /api/v1/desensitize: 批量脱敏消息列表
- POST /api/v1/desensitize/text: 单文本脱敏
"""

import time
import logging

from fastapi import APIRouter

from app.models.schemas import (
    DesensitizeRequest,
    DesensitizeResponse,
    DesensitizeTextRequest,
    DesensitizeTextResponse,
    ReplacedItem,
    Message,
)
from app.services.engine import desensitize_text, desensitize_messages

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

    result_messages, replaced = desensitize_messages(
        messages,
        rule_ids=rule_ids,
        skip_roles=opts.skip_roles,
        preserve_length=opts.preserve_length,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000

    return DesensitizeResponse(
        messages=[Message(**m) for m in result_messages],
        replaced=[ReplacedItem(**r) for r in replaced],
        metadata={
            "latency_ms": round(elapsed_ms, 2),
            "engine": "regex",
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

    result, replaced = desensitize_text(body.text, rule_ids=rule_ids)

    elapsed_ms = (time.perf_counter() - start) * 1000

    return DesensitizeTextResponse(
        text=result,
        replaced=[ReplacedItem(**r) for r in replaced],
        latency_ms=round(elapsed_ms, 2),
    )
