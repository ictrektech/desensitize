"""Image masking helpers."""

from __future__ import annotations

import base64
import binascii
import io
import math
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


def convex_hull(points: list[Point]) -> list[Point]:
    """Andrew's monotone chain; returns hull vertices in counter-clockwise order."""

    unique = sorted({(p.x, p.y) for p in points})
    if len(unique) <= 2:
        return [Point(x, y) for x, y in unique]

    def _cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[tuple[float, float]] = []
    for p in unique:
        while len(lower) >= 2 and _cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[tuple[float, float]] = []
    for p in reversed(unique):
        while len(upper) >= 2 and _cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return [Point(x, y) for x, y in lower[:-1] + upper[:-1]]


def expand_quad(quad: list[Point], padding: float) -> list[Point]:
    """Push each vertex away from the polygon centroid by `padding` pixels."""

    if not quad or padding <= 0:
        return list(quad)
    cx = sum(p.x for p in quad) / len(quad)
    cy = sum(p.y for p in quad) / len(quad)
    expanded: list[Point] = []
    for p in quad:
        dx, dy = p.x - cx, p.y - cy
        length = math.hypot(dx, dy) or 1.0
        expanded.append(Point(p.x + dx / length * padding, p.y + dy / length * padding))
    return expanded


def hull_region(quads: list[list[Point]], padding: float) -> MaskRegion | None:
    """Tight hull over padded source quads: skewed text gets a skewed mask."""

    points: list[Point] = []
    for quad in quads:
        points.extend(expand_quad(quad, padding))
    if not points:
        return None
    hull = convex_hull(points)
    xs = [p.x for p in hull]
    ys = [p.y for p in hull]
    if len(hull) < 3:
        # Degenerate (collinear) text line: fall back to its bounding box.
        hull = [
            Point(min(xs), min(ys)),
            Point(max(xs), min(ys)),
            Point(max(xs), max(ys)),
            Point(min(xs), max(ys)),
        ]
        xs = [p.x for p in hull]
        ys = [p.y for p in hull]
    box = Rect(min(xs), min(ys), max(xs), max(ys))
    return MaskRegion(box, hull)


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
            region = hull_region([b.quad for b in group], padding)
            if region is not None:
                regions.append(region)
    return regions


def apply_masks(image: Image.Image, regions: list[MaskRegion], fill: str = "#000000") -> Image.Image:
    masked = image.copy()
    draw = ImageDraw.Draw(masked)
    for region in regions:
        points = [(p.x, p.y) for p in region.quad]
        draw.polygon(points, fill=fill)
    return masked
