"""Conservative fallback masking for OCR-missed long text lines."""

from __future__ import annotations

import re

from PIL import Image, ImageOps

from app.services.image_layout import OcrBlock, Point, Rect
from app.services.image_masker import MaskRegion, hull_region


SENSITIVE_FIELD_LABELS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"公民身份(?:号码|号)?|身份证(?:号|号码)|证件(?:号|号码)"), "身份证字段邻近值"),
    (re.compile(r"手机|电话|联系方式|联系电话"), "电话字段邻近值"),
    (re.compile(r"邮箱|电子邮箱|E[-_ ]?mail", re.IGNORECASE), "邮箱字段邻近值"),
    (re.compile(r"住址|地址|详细地址|收货地址|寄件地址"), "地址字段邻近值"),
    (re.compile(r"银行卡|银行账号|账号"), "账号字段邻近值"),
    (re.compile(r"纳税人识别号|统一社会信用代码|税号"), "税号字段邻近值"),
    (re.compile(r"发票(?:代码|号码)|票据号码|机打号码|校验码"), "发票字段邻近值"),
    (re.compile(r"订单号|运单号|快递单号|物流单号|单号"), "物流字段邻近值"),
)


def detect_unrecognized_long_text_regions(
    image: Image.Image,
    blocks: list[OcrBlock],
    *,
    min_width_ratio: float = 0.28,
    min_width_px: int = 240,
    padding: float = 8.0,
) -> list[MaskRegion]:
    """Find long dark text rows that OCR did not return as blocks.

    RapidOCR can miss long mixed ASCII lines such as API keys. If no OCR block
    overlaps a sufficiently long text row, masking the full row is safer than
    returning the original pixels.
    """

    gray = ImageOps.grayscale(image)
    width, height = gray.size
    pixels = gray.load()
    row_threshold = max(8, int(width * 0.003))

    active_rows: list[int] = []
    for y in range(height):
        dark = 0
        for x in range(width):
            if pixels[x, y] < 150:
                dark += 1
                if dark >= row_threshold:
                    active_rows.append(y)
                    break

    bands = _merge_rows(active_rows, max_gap=3)
    regions: list[MaskRegion] = []
    min_width = max(min_width_px, width * min_width_ratio)

    for y1, y2 in bands:
        if y2 - y1 < 8 or y2 - y1 > max(120, height * 0.25):
            continue
        if _overlaps_ocr_block(y1, y2, blocks):
            continue

        dark_xs: list[int] = []
        for y in range(y1, y2 + 1):
            for x in range(width):
                if pixels[x, y] < 150:
                    dark_xs.append(x)
        if not dark_xs:
            continue

        x1 = min(dark_xs)
        x2 = max(dark_xs)
        if x2 - x1 < min_width:
            continue

        box = Rect(
            max(0.0, x1 - padding),
            max(0.0, y1 - padding),
            min(float(width), x2 + padding),
            min(float(height), y2 + padding),
        )
        quad = [
            Point(box.x1, box.y1),
            Point(box.x2, box.y1),
            Point(box.x2, box.y2),
            Point(box.x1, box.y2),
        ]
        regions.append(MaskRegion(box, quad))

    return regions


def detect_recheck_regions(
    image: Image.Image,
    blocks: list[OcrBlock],
    *,
    max_regions: int = 4,
    low_confidence: float = 0.55,
    min_width_ratio: float = 0.12,
    min_width_px: int = 80,
    padding: float = 12.0,
) -> list[tuple[MaskRegion, str]]:
    """Find small suspicious areas worth local high-resolution OCR.

    This is the third fallback described in the patent draft: narrow text bands
    rejected by the full-row mask and low-confidence OCR blocks are cropped from
    the original image, enlarged, and recognized again by the main engine.
    """

    candidates: list[tuple[MaskRegion, str, float]] = []
    for region in _narrow_text_band_regions(
        image,
        blocks,
        min_width_ratio=min_width_ratio,
        min_width_px=min_width_px,
        padding=padding,
    ):
        candidates.append((region, "narrow_text_band", region.box.width * region.box.height))

    for block in blocks:
        if block.score >= low_confidence:
            continue
        region = _region_for_blocks([block], padding=padding, image_width=image.width)
        candidates.append((region, "low_confidence_block", region.box.width * region.box.height))

    candidates.sort(key=lambda item: item[2], reverse=True)
    selected: list[tuple[MaskRegion, str]] = []
    seen: set[tuple[int, int, int, int, str]] = set()
    for region, reason, _ in candidates:
        key = (int(region.box.x1), int(region.box.y1), int(region.box.x2), int(region.box.y2), reason)
        if key in seen:
            continue
        seen.add(key)
        selected.append((region, reason))
        if len(selected) >= max_regions:
            break
    return selected


def detect_sensitive_field_value_regions(
    blocks: list[OcrBlock],
    *,
    image_width: int,
    padding: float = 4.0,
) -> list[tuple[MaskRegion, str]]:
    """Mask values near sensitive Chinese field labels.

    OCR may split or space out ID/invoice numbers so regex matching misses them.
    For document photos, the field label itself is a strong signal; mask the
    same-line value blocks to the right of that label.
    """

    regions: list[tuple[MaskRegion, str]] = []
    seen: set[tuple[int, int, int, int, str]] = set()
    lines: dict[int | None, list[OcrBlock]] = {}
    for block in blocks:
        lines.setdefault(block.line_id, []).append(block)

    for line in lines.values():
        line.sort(key=lambda b: b.bbox.x1)
        line_height = max((b.bbox.height for b in line), default=0.0)
        for index, block in enumerate(line):
            label = _label_name(block.text)
            if label is None:
                continue

            value_blocks = [
                candidate
                for candidate in line[index + 1 :]
                if candidate.bbox.x1 >= block.bbox.x2 - max(3.0, line_height * 0.25)
                and _looks_like_field_value(candidate.text)
            ]
            if not value_blocks and _inline_label_has_value(block.text):
                value_blocks = [block]
            if not value_blocks:
                region = _right_of_label_region(block, padding=padding, image_width=image_width)
                key = (
                    int(region.box.x1),
                    int(region.box.y1),
                    int(region.box.x2),
                    int(region.box.y2),
                    label,
                )
                if key in seen:
                    continue
                seen.add(key)
                regions.append((region, label))
                continue
            if not value_blocks:
                continue

            region = _region_for_blocks(value_blocks, padding=padding, image_width=image_width)
            key = (
                int(region.box.x1),
                int(region.box.y1),
                int(region.box.x2),
                int(region.box.y2),
                label,
            )
            if key in seen:
                continue
            seen.add(key)
            regions.append((region, label))

    return regions


def _merge_rows(rows: list[int], *, max_gap: int) -> list[tuple[int, int]]:
    if not rows:
        return []

    bands: list[tuple[int, int]] = []
    start = prev = rows[0]
    for row in rows[1:]:
        if row - prev <= max_gap:
            prev = row
            continue
        bands.append((start, prev))
        start = prev = row
    bands.append((start, prev))
    return bands


def _narrow_text_band_regions(
    image: Image.Image,
    blocks: list[OcrBlock],
    *,
    min_width_ratio: float,
    min_width_px: int,
    padding: float,
) -> list[MaskRegion]:
    gray = ImageOps.grayscale(image)
    width, height = gray.size
    pixels = gray.load()
    row_threshold = max(5, int(width * 0.002))
    active_rows: list[int] = []
    for y in range(height):
        dark = 0
        for x in range(width):
            if pixels[x, y] < 150:
                dark += 1
                if dark >= row_threshold:
                    active_rows.append(y)
                    break

    regions: list[MaskRegion] = []
    max_width = max(min_width_px, width * 0.28)
    min_width = max(min_width_px, width * min_width_ratio)
    for y1, y2 in _merge_rows(active_rows, max_gap=3):
        if y2 - y1 < 6 or y2 - y1 > max(90, height * 0.2):
            continue
        if _overlaps_ocr_block(y1, y2, blocks):
            continue
        dark_xs: list[int] = []
        for y in range(y1, y2 + 1):
            for x in range(width):
                if pixels[x, y] < 150:
                    dark_xs.append(x)
        if not dark_xs:
            continue
        x1, x2 = min(dark_xs), max(dark_xs)
        span = x2 - x1
        if span < min_width or span >= max_width:
            continue
        box = Rect(
            max(0.0, x1 - padding),
            max(0.0, y1 - padding),
            min(float(width), x2 + padding),
            min(float(height), y2 + padding),
        )
        quad = [
            Point(box.x1, box.y1),
            Point(box.x2, box.y1),
            Point(box.x2, box.y2),
            Point(box.x1, box.y2),
        ]
        regions.append(MaskRegion(box, quad))
    return regions


def _overlaps_ocr_block(y1: int, y2: int, blocks: list[OcrBlock]) -> bool:
    band_height = max(1, y2 - y1)
    for block in blocks:
        overlap = min(y2, block.bbox.y2) - max(y1, block.bbox.y1)
        if overlap <= 0:
            continue
        if overlap / band_height >= 0.45:
            return True
    return False


def _label_name(text: str) -> str | None:
    compact = re.sub(r"\s+", "", text or "")
    for pattern, label in SENSITIVE_FIELD_LABELS:
        if pattern.search(compact):
            return label
    return None


def _inline_label_has_value(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    return bool(re.search(r"[:：][A-Za-z0-9\u4e00-\u9fff]{2,}", compact))


def _looks_like_field_value(text: str) -> bool:
    compact = re.sub(r"\s+", "", text or "")
    if not compact:
        return False
    if re.search(r"\d{3,}", compact):
        return True
    if re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+", compact):
        return True
    if re.search(r"[A-Za-z0-9][A-Za-z0-9_-]{6,}", compact):
        return True
    if re.search(r"[\u4e00-\u9fff]{2,}", compact):
        return True
    return False


def _region_for_blocks(blocks: list[OcrBlock], *, padding: float, image_width: int) -> MaskRegion:
    # The hull keeps the mask tight around skewed field values; drawing beyond
    # the image edge is clipped by PIL and ledger crops are clamped separately.
    del image_width
    region = hull_region([b.quad for b in blocks], padding)
    if region is not None:
        return region
    x1 = min(b.bbox.x1 for b in blocks)
    y1 = min(b.bbox.y1 for b in blocks)
    x2 = max(b.bbox.x2 for b in blocks)
    y2 = max(b.bbox.y2 for b in blocks)
    box = Rect(x1, y1, x2, y2)
    quad = [
        Point(box.x1, box.y1),
        Point(box.x2, box.y1),
        Point(box.x2, box.y2),
        Point(box.x1, box.y2),
    ]
    return MaskRegion(box, quad)


def _right_of_label_region(block: OcrBlock, *, padding: float, image_width: int) -> MaskRegion:
    width = max(120.0, block.bbox.width * 2.4)
    x1 = block.bbox.x2 + padding
    x2 = min(float(image_width), x1 + width)
    y1 = max(0.0, block.bbox.y1 - padding)
    y2 = block.bbox.y2 + padding
    box = Rect(x1, y1, x2, y2)
    quad = [
        Point(box.x1, box.y1),
        Point(box.x2, box.y1),
        Point(box.x2, box.y2),
        Point(box.x1, box.y2),
    ]
    return MaskRegion(box, quad)
