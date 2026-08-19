"""End-to-end image desensitization service."""

from __future__ import annotations

from collections import Counter
import os
import time

from PIL import Image

from app.services.image_fallback import (
    detect_recheck_regions,
    detect_sensitive_field_value_regions,
    detect_unrecognized_long_text_regions,
)
from app.services.image_layout import OcrBlock, Point, Rect, rebuild_text, span_to_block_ids
from app.services.image_ledger import build_ledger, resolve_ledger_key
from app.services.image_matcher import ImageMatch, match_rebuilt_text_with_audit
from app.services.image_masker import (
    apply_masks,
    decode_image_base64,
    encode_image_base64,
    regions_for_matches,
    resize_for_ocr,
    scale_blocks,
)
from app.services.image_ocr import image_ocr_engine
from app.services.image_scene import classify_scene, effective_rule_ids
from app.services.ner_engine import ner_engine


def desensitize_image_base64(
    image_base64: str,
    *,
    mime_type: str = "image/jpeg",
    level: str = "standard",
    rule_ids: list[str] | None = None,
    ner: bool = False,
    adaptive: bool = False,
    reversible: bool = False,
    ledger_key: str | None = None,
    return_coordinates: bool = False,
    max_side: int = 1600,
) -> dict:
    del level  # reserved for future level-specific rule selection
    start = time.perf_counter()
    original = decode_image_base64(image_base64)
    ocr_image, scale = resize_for_ocr(original, max_side)
    detected_blocks = image_ocr_engine.detect(ocr_image)
    inverse_scale = 1.0 / scale if scale else 1.0
    blocks = scale_blocks(detected_blocks, inverse_scale)
    secondary = _secondary_ocr(original, blocks, enabled=_secondary_ocr_enabled(scale, blocks))
    if secondary["blocks"]:
        blocks.extend(secondary["blocks"])

    rebuilt = rebuild_text(blocks)
    scene = classify_scene(blocks, rebuilt) if adaptive else None
    match_result = match_rebuilt_text_with_audit(rebuilt, effective_rule_ids(scene, rule_ids))
    matches = match_result.matches

    replaced = _matches_to_replaced(matches)
    if ner:
        # MVP: use existing text NER for reporting/masking only when entities map
        # to OCR spans through exact rebuilt-text offsets.
        entities = ner_engine.detect(rebuilt.text)
        for entity in entities:
            block_ids = span_to_block_ids(rebuilt, entity["start"], entity["end"])
            if not block_ids:
                continue
            placeholder = "[PERSON_NAME]" if entity["kind"] == "PER" else "[ADDRESS]"
            matches.append(
                ImageMatch(
                    rule_id=f"ner_{entity['kind'].lower()}",
                    rule_name="NER 人名" if entity["kind"] == "PER" else "NER 地址",
                    placeholder=placeholder,
                    doc_start=entity["start"],
                    doc_end=entity["end"],
                    block_ids=block_ids,
                    matched_via="ner",
                )
            )
            replaced.append({"rule": "NER 人名" if entity["kind"] == "PER" else "NER 地址", "placeholder": placeholder, "occurrences": 1})

    policy = scene["policy"] if scene else None
    regions = regions_for_matches(blocks, matches)

    gate_regions = []
    gate_policy = os.getenv("DESENSITIZE_IMAGE_GATE_FAILURE_POLICY", "audit").lower()
    if gate_policy in {"conservative", "mask"}:
        gate_regions = regions_for_matches(
            blocks,
            [
                ImageMatch(
                    rule_id=item.rule_id,
                    rule_name=f"{item.rule_name}（校验失败嫌疑）",
                    placeholder="[SUSPECT_VALUE]",
                    doc_start=item.doc_start,
                    doc_end=item.doc_end,
                    block_ids=item.block_ids,
                    matched_via=f"{item.matched_via}_rejected",
                )
                for item in match_result.audit.rejected_candidates
                if item.block_ids
            ],
        )
    if gate_regions:
        regions.extend(gate_regions)
        replaced.append({"rule": "校验失败嫌疑区间", "placeholder": "[SUSPECT_VALUE]", "occurrences": len(gate_regions)})

    field_regions = []
    if policy is None or policy["field_fallback"]:
        field_regions = detect_sensitive_field_value_regions(blocks, image_width=original.width)
    if field_regions:
        regions.extend(region for region, _ in field_regions)
        for label in _group_labels(label for _, label in field_regions):
            replaced.append({"rule": label[0], "placeholder": "[FIELD_VALUE]", "occurrences": label[1]})

    fallback_regions = []
    if policy is None or policy["pixel_fallback"]:
        fallback_regions = detect_unrecognized_long_text_regions(original, blocks)
    if fallback_regions:
        regions.extend(fallback_regions)
        replaced.append(
            {
                "rule": "OCR 漏检长文本行",
                "placeholder": "[IMAGE_TEXT_LINE]",
                "occurrences": len(fallback_regions),
            }
        )

    ledger = None
    if reversible:
        ledger = build_ledger(original, regions, resolve_ledger_key(ledger_key))
    masked = apply_masks(original, regions)
    elapsed_ms = (time.perf_counter() - start) * 1000

    response = {
        "image_base64": encode_image_base64(masked, mime_type),
        "mime_type": mime_type,
        "replaced": replaced,
        "metadata": {
            "ocr_engine": "rapidocr",
            "ocr_blocks": len(blocks),
            "rebuilt_text_length": len(rebuilt.text),
            "normalized_matching": True,
            "matched_via": dict(Counter(m.matched_via for m in matches)),
            "suppressed_by_space": dict(match_result.audit.suppressed_by_space),
            "validator_rejected": len(match_result.audit.rejected_candidates),
            "gate_failure_policy": gate_policy,
            "adaptive": adaptive,
            "scene": (
                {
                    "type": scene["type"],
                    "signal_counts": scene["signal_counts"],
                    "policy": {key: value for key, value in scene["policy"].items()},
                }
                if scene
                else None
            ),
            "field_fallback_regions": len(field_regions),
            "fallback_masked_lines": len(fallback_regions),
            "secondary_ocr": {
                "enabled": secondary["enabled"],
                "regions": secondary["regions"],
                "blocks": len(secondary["blocks"]),
                "reasons": secondary["reasons"],
            },
            "resized": scale != 1.0,
            "scale": round(scale, 6),
            "ocr": image_ocr_engine.info(),
        },
        "latency_ms": round(elapsed_ms, 2),
    }
    if ledger is not None:
        response["ledger"] = ledger
    if return_coordinates:
        response["coordinates"] = [
            {
                "box": {"x1": r.box.x1, "y1": r.box.y1, "x2": r.box.x2, "y2": r.box.y2},
                "quad": [[p.x, p.y] for p in r.quad],
            }
            for r in regions
        ]
    return response


def _secondary_ocr_enabled(scale: float, blocks: list[OcrBlock]) -> bool:
    configured = os.getenv("DESENSITIZE_IMAGE_SECONDARY_OCR_ENABLED", "auto").lower()
    if configured in {"0", "false", "no", "off"}:
        return False
    if configured in {"1", "true", "yes", "on"}:
        return True
    return scale != 1.0 or any(block.score < 0.55 for block in blocks)


def _secondary_ocr(original: Image.Image, blocks: list[OcrBlock], *, enabled: bool) -> dict:
    if not enabled:
        return {"enabled": False, "regions": 0, "blocks": [], "reasons": {}}
    max_regions = int(os.getenv("DESENSITIZE_IMAGE_SECONDARY_OCR_MAX_REGIONS", "4"))
    target_short = int(os.getenv("DESENSITIZE_IMAGE_SECONDARY_OCR_TARGET_SHORT", "640"))
    recheck = detect_recheck_regions(original, blocks, max_regions=max_regions)
    new_blocks: list[OcrBlock] = []
    reasons: dict[str, int] = {}
    for region, reason in recheck:
        reasons[reason] = reasons.get(reason, 0) + 1
        crop_box = _safe_crop_box(region.box, original)
        if crop_box is None:
            continue
        crop = original.crop(crop_box)
        scale = _secondary_scale(crop, target_short)
        ocr_input = crop.resize((max(1, int(crop.width * scale)), max(1, int(crop.height * scale)))) if scale != 1.0 else crop
        detected = image_ocr_engine.detect(ocr_input)
        new_blocks.extend(_map_crop_blocks(detected, crop_box, scale))
    return {"enabled": True, "regions": len(recheck), "blocks": new_blocks, "reasons": reasons}


def _safe_crop_box(box: Rect, image: Image.Image) -> tuple[int, int, int, int] | None:
    x1 = max(0, int(box.x1))
    y1 = max(0, int(box.y1))
    x2 = min(image.width, int(box.x2))
    y2 = min(image.height, int(box.y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def _secondary_scale(image: Image.Image, target_short: int) -> float:
    short = min(image.width, image.height)
    if short <= 0 or short >= target_short:
        return 1.0
    return target_short / short


def _map_crop_blocks(blocks: list[OcrBlock], crop_box: tuple[int, int, int, int], scale: float) -> list[OcrBlock]:
    x_offset, y_offset = crop_box[0], crop_box[1]
    mapped: list[OcrBlock] = []
    for block in blocks:
        quad = [Point(p.x / scale + x_offset, p.y / scale + y_offset) for p in block.quad]
        bbox = Rect(
            block.bbox.x1 / scale + x_offset,
            block.bbox.y1 / scale + y_offset,
            block.bbox.x2 / scale + x_offset,
            block.bbox.y2 / scale + y_offset,
        )
        mapped.append(OcrBlock(block.text, quad, bbox, block.score, block.line_id, block.block_id))
    return mapped


def _matches_to_replaced(matches) -> list[dict]:
    grouped: dict[tuple[str, str], int] = {}
    for match in matches:
        key = (match.rule_name, match.placeholder)
        grouped[key] = grouped.get(key, 0) + 1
    return [
        {"rule": rule_name, "placeholder": placeholder, "occurrences": count}
        for (rule_name, placeholder), count in grouped.items()
    ]


def _group_labels(labels) -> list[tuple[str, int]]:
    grouped: dict[str, int] = {}
    for label in labels:
        grouped[label] = grouped.get(label, 0) + 1
    return list(grouped.items())
