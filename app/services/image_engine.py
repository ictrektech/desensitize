"""End-to-end image desensitization service."""

from __future__ import annotations

import time

from app.services.image_layout import rebuild_text, span_to_block_ids
from app.services.image_matcher import ImageMatch, match_rebuilt_text
from app.services.image_masker import (
    apply_masks,
    decode_image_base64,
    encode_image_base64,
    regions_for_matches,
    resize_for_ocr,
    scale_blocks,
)
from app.services.image_ocr import image_ocr_engine
from app.services.ner_engine import ner_engine


def desensitize_image_base64(
    image_base64: str,
    *,
    mime_type: str = "image/jpeg",
    level: str = "standard",
    rule_ids: list[str] | None = None,
    ner: bool = False,
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

    rebuilt = rebuild_text(blocks)
    matches = match_rebuilt_text(rebuilt, rule_ids)

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
                )
            )
            replaced.append({"rule": "NER 人名" if entity["kind"] == "PER" else "NER 地址", "placeholder": placeholder, "occurrences": 1})

    regions = regions_for_matches(blocks, matches)
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
            "resized": scale != 1.0,
            "scale": round(scale, 6),
            "ocr": image_ocr_engine.info(),
        },
        "latency_ms": round(elapsed_ms, 2),
    }
    if return_coordinates:
        response["coordinates"] = [
            {
                "box": {"x1": r.box.x1, "y1": r.box.y1, "x2": r.box.x2, "y2": r.box.y2},
                "quad": [[p.x, p.y] for p in r.quad],
            }
            for r in regions
        ]
    return response


def _matches_to_replaced(matches) -> list[dict]:
    grouped: dict[tuple[str, str], int] = {}
    for match in matches:
        key = (match.rule_name, match.placeholder)
        grouped[key] = grouped.get(key, 0) + 1
    return [
        {"rule": rule_name, "placeholder": placeholder, "occurrences": count}
        for (rule_name, placeholder), count in grouped.items()
    ]
