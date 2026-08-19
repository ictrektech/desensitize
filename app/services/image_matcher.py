"""Rule matching for reconstructed OCR text across multiple match spaces."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from app.services.image_layout import RebuiltText, compact_span_to_doc_span, span_to_block_ids
from app.services.rule_store import rule_store
from app.services.validators import VALIDATORS


@dataclass(frozen=True)
class ImageMatch:
    rule_id: str
    rule_name: str
    placeholder: str
    doc_start: int
    doc_end: int
    block_ids: list[int]
    matched_via: str = "text"


@dataclass(frozen=True)
class RejectedCandidate:
    rule_id: str
    rule_name: str
    doc_start: int
    doc_end: int
    block_ids: list[int]
    matched_via: str
    reason: str


@dataclass
class MatchAudit:
    suppressed_by_space: dict[str, int] = field(default_factory=dict)
    rejected_candidates: list[RejectedCandidate] = field(default_factory=list)


@dataclass
class MatchResult:
    matches: list[ImageMatch]
    audit: MatchAudit


def _overlaps(existing: list[ImageMatch], start: int, end: int) -> bool:
    return any(not (end <= item.doc_start or start >= item.doc_end) for item in existing)


def match_rebuilt_text(rebuilt: RebuiltText, rule_ids: list[str] | None = None) -> list[ImageMatch]:
    return match_rebuilt_text_with_audit(rebuilt, rule_ids).matches


def match_rebuilt_text_with_audit(rebuilt: RebuiltText, rule_ids: list[str] | None = None) -> MatchResult:
    rules = rule_store.get_all_rules(enabled_only=True)
    rules.sort(key=lambda r: r.get("priority", 0), reverse=True)

    matches: list[ImageMatch] = []
    audit = MatchAudit()
    for rule in rules:
        if rule_ids and rule["id"] not in rule_ids:
            continue

        compiled = rule_store.get_compiled(rule["id"])
        if compiled is None:
            continue

        _append_matches(matches, audit, rebuilt, rule, compiled, rebuilt.text, space="text")
        # A second pass on compact text fixes OCR block fragmentation where the
        # visible value is split by spaces/newlines between OCR blocks.
        if rebuilt.compact_text != rebuilt.text:
            _append_matches(matches, audit, rebuilt, rule, compiled, rebuilt.compact_text, space="compact")
        # Derived equal-length spaces catch OCR confusion. Spaces that broaden
        # numeric matching require a validator; reverse/API-key spaces can run
        # without one because their rules remain structurally restrictive.
        validator_name = rule.get("validator")
        for space in rebuilt.derived_spaces or []:
            if space.requires_validator and not validator_name:
                continue
            _append_matches(
                matches,
                audit,
                rebuilt,
                rule,
                compiled,
                space.text,
                space=space.name,
                validator_name=validator_name if space.requires_validator else None,
            )

    matches.sort(key=lambda m: (m.doc_start, -(m.doc_end - m.doc_start)))
    return MatchResult(matches, audit)


def _append_matches(
    output: list[ImageMatch],
    audit: MatchAudit,
    rebuilt: RebuiltText,
    rule: dict,
    compiled: re.Pattern,
    text: str,
    *,
    space: str,
    validator_name: str | None = None,
) -> None:
    validator = VALIDATORS.get(validator_name) if validator_name else None
    for match in compiled.finditer(text):
        if space == "text":
            doc_start, doc_end = match.start(), match.end()
        else:
            doc_start, doc_end = compact_span_to_doc_span(rebuilt, match.start(), match.end())
        if _overlaps(output, doc_start, doc_end):
            audit.suppressed_by_space[space] = audit.suppressed_by_space.get(space, 0) + 1
            continue
        if validator is not None:
            value = match.group(1) if match.re.groups else match.group(0)
            if not validator(value):
                block_ids = span_to_block_ids(rebuilt, doc_start, doc_end)
                audit.rejected_candidates.append(
                    RejectedCandidate(
                        rule_id=rule["id"],
                        rule_name=rule["name"],
                        doc_start=doc_start,
                        doc_end=doc_end,
                        block_ids=block_ids,
                        matched_via=space,
                        reason="validator_failed",
                    )
                )
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
                matched_via=space,
            )
        )
