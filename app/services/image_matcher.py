"""Rule matching for reconstructed OCR text."""

from __future__ import annotations

from dataclasses import dataclass
import re

from app.services.image_layout import RebuiltText, compact_span_to_doc_span, span_to_block_ids
from app.services.rule_store import rule_store


@dataclass(frozen=True)
class ImageMatch:
    rule_id: str
    rule_name: str
    placeholder: str
    doc_start: int
    doc_end: int
    block_ids: list[int]


def _overlaps(existing: list[ImageMatch], start: int, end: int) -> bool:
    return any(not (end <= item.doc_start or start >= item.doc_end) for item in existing)


def match_rebuilt_text(rebuilt: RebuiltText, rule_ids: list[str] | None = None) -> list[ImageMatch]:
    rules = rule_store.get_all_rules(enabled_only=True)
    rules.sort(key=lambda r: r.get("priority", 0), reverse=True)

    matches: list[ImageMatch] = []
    for rule in rules:
        if rule_ids and rule["id"] not in rule_ids:
            continue

        compiled = rule_store.get_compiled(rule["id"])
        if compiled is None:
            continue

        _append_matches(matches, rebuilt, rule, compiled, rebuilt.text, compact=False)
        # A second pass on compact text fixes OCR block fragmentation where the
        # visible value is split by spaces/newlines between OCR blocks.
        if rebuilt.compact_text != rebuilt.text:
            _append_matches(matches, rebuilt, rule, compiled, rebuilt.compact_text, compact=True)

    matches.sort(key=lambda m: (m.doc_start, -(m.doc_end - m.doc_start)))
    return matches


def _append_matches(
    output: list[ImageMatch],
    rebuilt: RebuiltText,
    rule: dict,
    compiled: re.Pattern,
    text: str,
    *,
    compact: bool,
) -> None:
    for match in compiled.finditer(text):
        if compact:
            doc_start, doc_end = compact_span_to_doc_span(rebuilt, match.start(), match.end())
        else:
            doc_start, doc_end = match.start(), match.end()
        if _overlaps(output, doc_start, doc_end):
            continue
        block_ids = span_to_block_ids(rebuilt, doc_start, doc_end)
        if not block_ids:
            continue
        output.append(
            ImageMatch(
                rule_id=rule["id"],
                rule_name=rule["name"],
                placeholder=rule["placeholder"],
                doc_start=doc_start,
                doc_end=doc_end,
                block_ids=block_ids,
            )
        )
