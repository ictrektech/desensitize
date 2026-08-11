"""Image masking helpers."""

from __future__ import annotations

import base64
import binascii
import io
from dataclasses import dataclass

from PIL import Image, ImageDraw

from app.services.image_layout import OcrBlock, Point, Rect
from app.services.image_matcher import ImageMatch


@dataclass(frozen=True)
class MaskRegion:
    box: Rect
    quad: list[Point]


def decode_image_base64(image_base64: str) -> Image.Image:
    if "," in image_base64 and image_base64.split(",", 1)[0].startswith("data:"):
        image_base64 = image_base64.split(",", 1)[1]
    try:
        raw = base64.b64decode(image_base64, validate=False)
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except (binascii.Error, OSError) as exc:
        raise ValueError("invalid base64 image") from exc


def encode_image_base64(image: Image.Image, mime_type: str) -> str:
    fmt = "PNG" if mime_type.lower().endswith("png") else "JPEG"
    buffer = io.BytesIO()
    save_kwargs = {"quality": 92} if fmt == "JPEG" else {}
    image.save(buffer, format=fmt, **save_kwargs)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def resize_for_ocr(image: Image.Image, max_side: int) -> tuple[Image.Image, float]:
    width, height = image.size
    largest = max(width, height)
    if max_side <= 0 or largest <= max_side:
        return image, 1.0
    scale = max_side / largest
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size), scale


def scale_blocks(blocks: list[OcrBlock], inverse_scale: float) -> list[OcrBlock]:
    if inverse_scale == 1.0:
        return blocks
    scaled: list[OcrBlock] = []
    for block in blocks:
        quad = [Point(p.x * inverse_scale, p.y * inverse_scale) for p in block.quad]
        bbox = Rect(
            block.bbox.x1 * inverse_scale,
            block.bbox.y1 * inverse_scale,
            block.bbox.x2 * inverse_scale,
            block.bbox.y2 * inverse_scale,
        )
        scaled.append(OcrBlock(block.text, quad, bbox, block.score, block.line_id, block.block_id))
    return scaled


def regions_for_matches(blocks: list[OcrBlock], matches: list[ImageMatch], padding: float = 3.0) -> list[MaskRegion]:
    regions: list[MaskRegion] = []
    by_id = {b.block_id: b for b in blocks}
    for match in matches:
        line_groups: dict[int | None, list[OcrBlock]] = {}
        for block_id in match.block_ids:
            block = by_id.get(block_id)
            if block is None:
                continue
            line_groups.setdefault(block.line_id, []).append(block)
        for group in line_groups.values():
            if not group:
                continue
            x1 = min(b.bbox.x1 for b in group) - padding
            y1 = min(b.bbox.y1 for b in group) - padding
            x2 = max(b.bbox.x2 for b in group) + padding
            y2 = max(b.bbox.y2 for b in group) + padding
            box = Rect(x1, y1, x2, y2)
            quad = [Point(x1, y1), Point(x2, y1), Point(x2, y2), Point(x1, y2)]
            regions.append(MaskRegion(box, quad))
    return regions


def apply_masks(image: Image.Image, regions: list[MaskRegion], fill: str = "#000000") -> Image.Image:
    masked = image.copy()
    draw = ImageDraw.Draw(masked)
    for region in regions:
        points = [(p.x, p.y) for p in region.quad]
        draw.polygon(points, fill=fill)
    return masked
