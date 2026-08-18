import unittest

from app.services.image_layout import OcrBlock, Point, Rect
from app.services.image_matcher import ImageMatch
from app.services.image_masker import regions_for_matches


def _shoelace(points):
    total = 0.0
    count = len(points)
    for i in range(count):
        x1, y1 = points[i].x, points[i].y
        x2, y2 = points[(i + 1) % count].x, points[(i + 1) % count].y
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _match(block_ids):
    return ImageMatch(
        rule_id="phone_cn",
        rule_name="手机号",
        placeholder="[PHONE_NUMBER]",
        doc_start=0,
        doc_end=9,
        block_ids=block_ids,
    )


class QuadMaskingTest(unittest.TestCase):
    def test_skewed_blocks_get_tight_hull(self):
        b1 = OcrBlock(
            text="138",
            quad=[Point(10, 20), Point(110, 30), Point(110, 60), Point(10, 50)],
            bbox=Rect(10, 20, 110, 60),
            score=0.99,
            line_id=0,
            block_id=0,
        )
        b2 = OcrBlock(
            text="00138000",
            quad=[Point(120, 32), Point(220, 42), Point(220, 72), Point(120, 62)],
            bbox=Rect(120, 32, 220, 72),
            score=0.99,
            line_id=0,
            block_id=1,
        )
        regions = regions_for_matches([b1, b2], [_match([0, 1])])
        self.assertEqual(len(regions), 1)
        region = regions[0]
        self.assertGreaterEqual(len(region.quad), 4)
        hull_area = _shoelace(region.quad)
        bbox_area = region.box.width * region.box.height
        # A skewed hull must be strictly tighter than its bounding rectangle.
        self.assertLess(hull_area, bbox_area * 0.95)
        # The reported box is exactly the hull's axis-aligned bounding box.
        self.assertAlmostEqual(min(p.x for p in region.quad), region.box.x1)
        self.assertAlmostEqual(max(p.x for p in region.quad), region.box.x2)
        self.assertAlmostEqual(min(p.y for p in region.quad), region.box.y1)
        self.assertAlmostEqual(max(p.y for p in region.quad), region.box.y2)

    def test_axis_blocks_degrade_to_rectangle(self):
        b1 = OcrBlock(
            text="138",
            quad=[Point(10, 10), Point(110, 10), Point(110, 40), Point(10, 40)],
            bbox=Rect(10, 10, 110, 40),
            score=0.99,
            line_id=0,
            block_id=0,
        )
        b2 = OcrBlock(
            text="00138000",
            quad=[Point(120, 10), Point(220, 10), Point(220, 40), Point(120, 40)],
            bbox=Rect(120, 10, 220, 40),
            score=0.99,
            line_id=0,
            block_id=1,
        )
        regions = regions_for_matches([b1, b2], [_match([0, 1])])
        self.assertEqual(len(regions), 1)
        region = regions[0]
        hull_area = _shoelace(region.quad)
        self.assertAlmostEqual(hull_area, region.box.width * region.box.height, places=3)


if __name__ == "__main__":
    unittest.main()
