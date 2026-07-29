"""
engine.py
==========

脱敏引擎核心。

负责：
- 执行正则规则匹配与替换
- 支持按规则名称过滤
- 支持中文数字归一化预处理
- 记录替换统计
"""

import re
import time
import logging
from typing import Optional

from app.services.rule_store import rule_store

logger = logging.getLogger("ictrek-desensitize.engine")

# 中文数字到阿拉伯数字的映射
_CHINESE_NUM_MAP = {
    "零": "0", "〇": "0", "O": "0", "o": "0",
    "一": "1", "幺": "1",
    "二": "2", "两": "2",
    "三": "3", "四": "4", "五": "5",
    "六": "6", "七": "7", "八": "8", "九": "9",
}


def preprocess_chinese_numbers(text: str) -> str:
    """
    预处理: 将连续的中文数字归一化为阿拉伯数字。
    只处理 5 位及以上的连续数字序列（如手机号、身份证号）。
    """
    if not text:
        return text

    result = []
    i = 0
    while i < len(text):
        char = text[i]
        if char in _CHINESE_NUM_MAP:
            num_buffer = [_CHINESE_NUM_MAP[char]]
            j = i + 1
            while j < len(text) and text[j] in _CHINESE_NUM_MAP:
                num_buffer.append(_CHINESE_NUM_MAP[text[j]])
                j += 1

            if len(num_buffer) >= 5:
                result.append("".join(num_buffer))
            else:
                result.append(text[i:j])
            i = j
        else:
            result.append(char)
            i += 1

    return "".join(result)


def desensitize_text(
    text: str,
    rule_ids: Optional[list[str]] = None,
    preserve_length: bool = False,
) -> tuple[str, list[dict]]:
    """
    对单条文本执行脱敏。

    Args:
        text: 原始文本
        rule_ids: 只使用这些 ID 的规则（None = 全部启用的规则）
        preserve_length: 占位符是否填充到与原文等长

    Returns:
        (脱敏后的文本, 替换记录列表)
    """
    if not text:
        return text, []

    # 预处理: 中文数字归一化
    processed = preprocess_chinese_numbers(text)

    rules = rule_store.get_all_rules(enabled_only=True)
    # 按优先级降序排列
    rules.sort(key=lambda r: r.get("priority", 0), reverse=True)

    replaced = []
    for rule in rules:
        if rule_ids and rule["id"] not in rule_ids:
            continue

        compiled = rule_store.get_compiled(rule["id"])
        if compiled is None:
            continue

        matches = list(compiled.finditer(processed))
        if not matches:
            continue

        placeholder = rule["placeholder"]
        if preserve_length:
            def _pad(m):
                length = len(m.group(0))
                return placeholder[:length].ljust(length, "*") if len(placeholder) < length else placeholder
            processed = compiled.sub(_pad, processed)
        else:
            # 对于有反向引用的规则（如 URL 参数），使用 lambda
            if "\\1" in placeholder or "\\2" in placeholder:
                processed = compiled.sub(lambda m: _expand_backrefs(placeholder, m), processed)
            else:
                processed = compiled.sub(placeholder, processed)

        replaced.append({
            "rule": rule["name"],
            "placeholder": placeholder,
            "occurrences": len(matches),
        })

    return processed, replaced


def _expand_backrefs(template: str, match: re.Match) -> str:
    """展开替换模板中的 \\1 \\2 等反向引用。"""
    result = template
    for i, g in enumerate(match.groups(), 1):
        if g is not None:
            result = result.replace(f"\\{i}", g)
    return result


def desensitize_messages(
    messages: list[dict],
    rule_ids: Optional[list[str]] = None,
    skip_roles: Optional[list[str]] = None,
    preserve_length: bool = False,
) -> tuple[list[dict], list[dict]]:
    """
    对消息列表执行脱敏。

    Args:
        messages: 消息列表 [{role, content}]
        rule_ids: 只使用这些 ID 的规则
        skip_roles: 跳过这些角色的消息
        preserve_length: 占位符是否填充到与原文等长

    Returns:
        (脱敏后的消息列表, 替换记录列表)
    """
    if skip_roles is None:
        skip_roles = ["assistant"]

    all_replaced = []
    result_messages = []

    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role in skip_roles or not content:
            result_messages.append(msg)
            continue

        sanitized, replaced = desensitize_text(content, rule_ids, preserve_length)
        result_messages.append({"role": role, "content": sanitized})
        all_replaced.extend(replaced)

    return result_messages, all_replaced
