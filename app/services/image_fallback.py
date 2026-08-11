"""Conservative fallback masking for OCR-missed long text lines."""

from __future__ import annotations

from PIL import Image, ImageOps

from app.services.image_layout import OcrBlock, Point, Rect
from app.services.image_masker import MaskRegion


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


def _overlaps_ocr_block(y1: int, y2: int, blocks: list[OcrBlock]) -> bool:
    band_height = max(1, y2 - y1)
    for block in blocks:
        overlap = min(y2, block.bbox.y2) - max(y1, block.bbox.y1)
        if overlap <= 0:
            continue
        if overlap / band_height >= 0.45:
            return True
    return False
