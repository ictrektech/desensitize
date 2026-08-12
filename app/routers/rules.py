"""
rules.py
========

规则管理路由。

提供:
- GET /api/v1/rules: 列出所有规则
- GET /api/v1/rules/{rule_id}: 查看单个规则
- POST /api/v1/rules: 创建自定义规则
- PUT /api/v1/rules/{rule_id}: 更新规则（内置规则仅支持启停，自定义规则支持完整更新）
- DELETE /api/v1/rules/{rule_id}: 删除自定义规则
- POST /api/v1/rules/test: 测试规则正则
"""

import re
import logging

from fastapi import APIRouter, HTTPException

from app.models.schemas import RuleOut, RuleCreate, RuleUpdate
from app.services.rule_store import rule_store

logger = logging.getLogger("ictrek-desensitize.rules")

router = APIRouter(prefix="/api/v1/rules", tags=["rules"])


@router.get("", response_model=list[RuleOut], summary="列出所有规则")
async def list_rules(enabled_only: bool = False):
    """列出所有规则（内置 + 自定义）。"""
    return rule_store.get_all_rules(enabled_only=enabled_only)


@router.get("/builtin", response_model=list[RuleOut], summary="列出内置规则")
async def list_builtin_rules():
    return rule_store.get_builtin_rules()


@router.get("/custom", response_model=list[RuleOut], summary="列出自定义规则")
async def list_custom_rules():
    return rule_store.get_custom_rules()


@router.get("/{rule_id}", response_model=RuleOut, summary="查看单个规则")
async def get_rule(rule_id: str):
    rule = rule_store.get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return rule


@router.post("", response_model=RuleOut, status_code=201, summary="创建自定义规则")
async def create_rule(body: RuleCreate):
    # 验证正则是否合法
    try:
        re.compile(body.pattern)
    except re.error as e:
        raise HTTPException(status_code=422, detail=f"Invalid regex: {e}")

    rule_dict = body.model_dump()
    created = rule_store.add_custom_rule(rule_dict)
    logger.info("创建自定义规则: %s", created["id"])
    return created


@router.put("/{rule_id}", response_model=RuleOut, summary="更新规则")
async def update_rule(rule_id: str, body: RuleUpdate):
    existing = rule_store.get_rule(rule_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")

    updates = body.model_dump(exclude_none=True)
    if existing.get("builtin"):
        if set(updates) != {"enabled"}:
            raise HTTPException(status_code=403, detail="Builtin rules only support enabled updates")
        updated = rule_store.update_builtin_enabled(rule_id, updates["enabled"])
        logger.info("更新内置规则启停状态: %s -> %s", rule_id, updates["enabled"])
        return updated

    if "pattern" in updates:
        try:
            re.compile(updates["pattern"])
        except re.error as e:
            raise HTTPException(status_code=422, detail=f"Invalid regex: {e}")

    updated = rule_store.update_custom_rule(rule_id, updates)
    logger.info("更新自定义规则: %s", rule_id)
    return updated


@router.delete("/{rule_id}", status_code=204, summary="删除自定义规则")
async def delete_rule(rule_id: str):
    existing = rule_store.get_rule(rule_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    if existing.get("builtin"):
        raise HTTPException(status_code=403, detail="Cannot delete builtin rules")

    if not rule_store.delete_custom_rule(rule_id):
        raise HTTPException(status_code=500, detail="Failed to delete rule")
    logger.info("删除自定义规则: %s", rule_id)


@router.post("/test", summary="测试正则表达式")
async def test_pattern(pattern: str, text: str, placeholder: str = "[REDACTED]"):
    """
    测试正则表达式是否匹配给定文本，并返回脱敏后的结果。
    """
    try:
        compiled = re.compile(pattern)
    except re.error as e:
        raise HTTPException(status_code=422, detail=f"Invalid regex: {e}")

    matches = list(compiled.finditer(text))
    result = compiled.sub(placeholder, text)

    return {
        "matched": len(matches) > 0,
        "matches": [
            {
                "value": m.group(0),
                "start": m.start(),
                "end": m.end(),
            }
            for m in matches
        ],
        "result": result,
        "match_count": len(matches),
    }
