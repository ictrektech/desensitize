"""OCR layout reconstruction for image desensitization.

The important invariant is that rule matching never runs on isolated OCR blocks.
OCR engines often split one sensitive value into multiple blocks, so we rebuild
line/document text and preserve offset mappings back to source boxes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
import unicodedata


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Rect:
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def cy(self) -> float:
        return (self.y1 + self.y2) / 2


@dataclass
class OcrBlock:
    text: str
    quad: list[Point]
    bbox: Rect
    score: float = 1.0
    line_id: int | None = None
    block_id: int | None = None


@dataclass(frozen=True)
class CharMap:
    doc_start: int
    doc_end: int
    block_id: int | None
    block_char_start: int
    block_char_end: int
    synthetic: bool = False


# Common OCR confusions between digits and lookalike letters. Mapping is 1:1,
# so offsets into confused_text align with compact_to_doc directly.
CONFUSION_MAP = {
    "O": "0",
    "o": "0",
    "l": "1",
    "I": "1",
    "i": "1",
    "Z": "2",
    "z": "2",
    "S": "5",
    "s": "5",
    "G": "6",
    "B": "8",
    "g": "9",
}

REVERSE_CONFUSION_MAP = {
    "0": "O",
    "1": "i",
    "2": "Z",
    "5": "S",
    "6": "G",
    "8": "B",
    "9": "g",
}


@dataclass(frozen=True)
class DerivedSpace:
    name: str
    text: str
    requires_validator: bool = False


@dataclass
class RebuiltText:
    text: str
    blocks: list[OcrBlock]
    char_maps: list[CharMap]
    block_ranges: dict[int, tuple[int, int]]
    compact_text: str
    compact_to_doc: list[int]
    confused_text: str = ""
    derived_spaces: list[DerivedSpace] | None = None


def rect_from_quad(quad: list[Point]) -> Rect:
    xs = [p.x for p in quad]
    ys = [p.y for p in quad]
    return Rect(min(xs), min(ys), max(xs), max(ys))


def _line_threshold(block: OcrBlock) -> float:
    return max(8.0, block.bbox.height * 0.65)


def rebuild_text(blocks: list[OcrBlock]) -> RebuiltText:
    """Rebuild document text from OCR blocks and keep char-to-block mappings."""
    clean_blocks = [b for b in blocks if b.text and b.text.strip()]
    for i, block in enumerate(clean_blocks):
        block.block_id = i
        if not block.quad:
            block.quad = [
                Point(block.bbox.x1, block.bbox.y1),
                Point(block.bbox.x2, block.bbox.y1),
                Point(block.bbox.x2, block.bbox.y2),
                Point(block.bbox.x1, block.bbox.y2),
            ]

    lines: list[list[OcrBlock]] = []
    for block in sorted(clean_blocks, key=lambda b: (b.bbox.cy, b.bbox.x1)):
        target: list[OcrBlock] | None = None
        for line in lines:
            avg_cy = sum(b.bbox.cy for b in line) / len(line)
            threshold = max(_line_threshold(block), sum(_line_threshold(b) for b in line) / len(line))
            if abs(block.bbox.cy - avg_cy) <= threshold:
                target = line
                break
        if target is None:
            target = []
            lines.append(target)
        target.append(block)

    text_parts: list[str] = []
    char_maps: list[CharMap] = []
    block_ranges: dict[int, tuple[int, int]] = {}
    doc_pos = 0

    for line_id, line in enumerate(lines):
        line.sort(key=lambda b: b.bbox.x1)
        for block_index, block in enumerate(line):
            block.line_id = line_id
            if block_index > 0:
                # Keep a synthetic separator for natural language/NER. Compact
                # matching removes it, so split phone/id/key values still match.
                text_parts.append(" ")
                char_maps.append(CharMap(doc_pos, doc_pos + 1, None, 0, 0, synthetic=True))
                doc_pos += 1

            normalized = unicodedata.normalize("NFKC", block.text.strip())
            start = doc_pos
            text_parts.append(normalized)
            end = start + len(normalized)
            char_maps.append(
                CharMap(
                    doc_start=start,
                    doc_end=end,
                    block_id=block.block_id,
                    block_char_start=0,
                    block_char_end=len(normalized),
                )
            )
            if block.block_id is not None:
                block_ranges[block.block_id] = (start, end)
            doc_pos = end

        if line_id != len(lines) - 1:
            text_parts.append("\n")
            char_maps.append(CharMap(doc_pos, doc_pos + 1, None, 0, 0, synthetic=True))
            doc_pos += 1

    text = "".join(text_parts)
    compact_chars: list[str] = []
    compact_to_doc: list[int] = []
    for i, char in enumerate(text):
        if char.isspace():
            continue
        compact_chars.append(char)
        compact_to_doc.append(i)

    compact_text = "".join(compact_chars)
    confused_text = "".join(CONFUSION_MAP.get(char, char) for char in compact_text)
    derived_spaces = _build_derived_spaces(compact_text)

    return RebuiltText(
        text=text,
        blocks=clean_blocks,
        char_maps=char_maps,
        block_ranges=block_ranges,
        compact_text=compact_text,
        compact_to_doc=compact_to_doc,
        confused_text=confused_text,
        derived_spaces=derived_spaces,
    )


def _build_derived_spaces(compact_text: str) -> list[DerivedSpace]:
    spaces: list[DerivedSpace] = []
    for name, mapping, requires_validator in _configured_confusion_maps():
        derived = "".join(mapping.get(char, char) for char in compact_text)
        if derived != compact_text:
            spaces.append(DerivedSpace(name, derived, requires_validator))
    return spaces


def _configured_confusion_maps() -> list[tuple[str, dict[str, str], bool]]:
    maps: list[tuple[str, dict[str, str], bool]] = [("confused", dict(CONFUSION_MAP), True)]
    if os.getenv("DESENSITIZE_IMAGE_REVERSE_CONFUSION_ENABLED", "true").lower() in {"1", "true", "yes", "on"}:
        maps.append(("reverse_confused", dict(REVERSE_CONFUSION_MAP), False))

    raw = os.getenv("DESENSITIZE_IMAGE_CONFUSION_MAPS_JSON", "").strip()
    if not raw:
        return maps
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return maps
    if not isinstance(data, list):
        return maps
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        mapping = item.get("map")
        if not isinstance(mapping, dict):
            continue
        one_to_one = {str(k): str(v) for k, v in mapping.items() if len(str(k)) == 1 and len(str(v)) == 1}
        if not one_to_one:
            continue
        name = str(item.get("name") or f"custom_confused_{index + 1}")
        requires_validator = bool(item.get("requires_validator", True))
        maps.append((name, one_to_one, requires_validator))
    return maps


def span_to_block_ids(rebuilt: RebuiltText, start: int, end: int) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for mapping in rebuilt.char_maps:
        if mapping.synthetic or mapping.block_id is None:
            continue
        if mapping.doc_end <= start or mapping.doc_start >= end:
            continue
        if mapping.block_id not in seen:
            seen.add(mapping.block_id)
            ids.append(mapping.block_id)
    return ids


def compact_span_to_doc_span(rebuilt: RebuiltText, start: int, end: int) -> tuple[int, int]:
    if start < 0 or end <= start or end > len(rebuilt.compact_to_doc):
        raise ValueError("invalid compact span")
    return rebuilt.compact_to_doc[start], rebuilt.compact_to_doc[end - 1] + 1
