"""Lightweight document-type classification driving adaptive redaction policies.

Classification relies only on OCR text signals (field labels / keywords), so it
adds no extra model inference on weak VOS hosts. The fallback-safe default is
`generic`: full rules and both fallback layers stay enabled.
"""

from __future__ import annotations

import re

from app.services.image_layout import OcrBlock, RebuiltText

SCENE_TYPES = ("id_document", "invoice", "shipping_label", "config_screenshot", "generic")

_SCENE_SIGNALS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("invoice", re.compile(r"发票|增值税|价税合计|开票|票据号码|机打号码|校验码|统一社会信用代码")),
    ("shipping_label", re.compile(r"收货|寄件|收件|快递|运单|物流|派送|扫码取件|生鲜|保价")),
    ("id_document", re.compile(r"公民身份号码|居民身份证|中华人民共和国|签发机关|有效期限|出生日期|民族")),
    (
        "config_screenshot",
        re.compile(
            r"api[_-]?key|apikey|token|secret|passwd|password|credential|Bearer\s|https?://|"
            r"\.env|\.ya?ml|\.json|config|localhost|\d{1,3}(?:\.\d{1,3}){3}",
            re.IGNORECASE,
        ),
    ),
)

SCENE_POLICIES: dict[str, dict] = {
    # rule_categories None means all rules stay active.
    "id_document": {"rule_categories": None, "field_fallback": True, "pixel_fallback": True, "ner_hint": True},
    "invoice": {"rule_categories": None, "field_fallback": True, "pixel_fallback": True, "ner_hint": False},
    "shipping_label": {"rule_categories": None, "field_fallback": True, "pixel_fallback": True, "ner_hint": True},
    "config_screenshot": {"rule_categories": ["api_key", "pii"], "field_fallback": False, "pixel_fallback": True, "ner_hint": False},
    "generic": {"rule_categories": None, "field_fallback": True, "pixel_fallback": True, "ner_hint": True},
}


def classify_scene(blocks: list[OcrBlock], rebuilt: RebuiltText | None = None) -> dict:
    """Classify the document type from OCR block text signals.

    A scene wins only with at least two signal blocks and a strict lead over
    every other scene; otherwise the conservative `generic` policy applies.
    """

    del rebuilt  # reserved for future layout-based signals
    scores: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    for block in blocks:
        compact = re.sub(r"\s+", "", block.text or "")
        if not compact:
            continue
        for scene, pattern in _SCENE_SIGNALS:
            if pattern.search(compact):
                scores[scene] = scores.get(scene, 0) + 1
                samples.setdefault(scene, []).append(compact[:24])

    winner = None
    if scores:
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        top_scene, top_count = ranked[0]
        tied = len(ranked) > 1 and ranked[1][1] == top_count
        if top_count >= 2 and not tied:
            winner = top_scene

    scene_type = winner or "generic"
    return {
        "type": scene_type,
        "signal_counts": scores,
        "signal_samples": {k: v[:3] for k, v in samples.items()},
        "policy": SCENE_POLICIES[scene_type],
    }


def effective_rule_ids(scene: dict | None, rule_ids: list[str] | None) -> list[str] | None:
    """Intersect the caller's rule selection with the scene policy categories."""

    if not scene or scene["policy"]["rule_categories"] is None:
        return rule_ids
    from app.services.rule_store import rule_store

    allowed = set(scene["policy"]["rule_categories"])
    candidates = [r["id"] for r in rule_store.get_all_rules(enabled_only=True) if r.get("category") in allowed]
    if not rule_ids:
        return candidates
    keep = set(candidates)
    return [r for r in rule_ids if r in keep]
