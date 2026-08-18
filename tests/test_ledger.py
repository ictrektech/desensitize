import os
import unittest

from PIL import Image

from app.services.image_ledger import build_ledger, resolve_ledger_key, restore_image
from app.services.image_layout import Point, Rect
from app.services.image_masker import MaskRegion, apply_masks, encode_image_base64


def _region(x1, y1, x2, y2):
    box = Rect(x1, y1, x2, y2)
    quad = [Point(x1, y1), Point(x2, y1), Point(x2, y2), Point(x1, y2)]
    return MaskRegion(box, quad)


class LedgerTest(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGB", (200, 120))
        for x in range(200):
            for y in range(120):
                self.image.putpixel((x, y), ((x * 7) % 256, (y * 5) % 256, (x + y) % 256))
        self.key = os.urandom(32).hex()

    def test_roundtrip_restores_original_pixels(self):
        regions = [_region(10, 10, 80, 60), _region(100, 20, 180, 100)]
        ledger = build_ledger(self.image, regions, bytes.fromhex(self.key))
        self.assertEqual(ledger["version"], 1)
        self.assertEqual(ledger["alg"], "AES-256-GCM")
        self.assertEqual(ledger["region_count"], 2)

        masked = apply_masks(self.image, regions)
        restored, report = restore_image(
            encode_image_base64(masked, "image/png"), ledger, bytes.fromhex(self.key)
        )
        self.assertTrue(all(item["restored"] for item in report))
        self.assertEqual(restored.size, self.image.size)
        self.assertEqual(restored.tobytes(), self.image.tobytes())

    def test_out_of_bounds_region_clamped_or_skipped(self):
        regions = [_region(-20, -10, 60, 60), _region(300, 50, 400, 90)]
        ledger = build_ledger(self.image, regions, bytes.fromhex(self.key))
        boxes = [entry["box"] for entry in ledger["regions"]]
        self.assertEqual(ledger["region_count"], 1)
        self.assertEqual(boxes[0]["x1"], 0)
        self.assertEqual(boxes[0]["y1"], 0)

    def test_wrong_key_fails_per_region(self):
        regions = [_region(10, 10, 80, 60)]
        ledger = build_ledger(self.image, regions, bytes.fromhex(self.key))
        masked = apply_masks(self.image, regions)
        _, report = restore_image(
            encode_image_base64(masked, "image/png"), ledger, bytes.fromhex(os.urandom(32).hex())
        )
        self.assertEqual(len(report), 1)
        self.assertFalse(report[0]["restored"])
        self.assertIn("decrypt failed", report[0]["error"])

    def test_resolve_ledger_key_rules(self):
        os.environ.pop("DESENSITIZE_LEDGER_KEY", None)
        with self.assertRaises(ValueError):
            resolve_ledger_key(None)
        with self.assertRaises(ValueError):
            resolve_ledger_key("abcd")
        with self.assertRaises(ValueError):
            resolve_ledger_key("aa" * 16)
        self.assertEqual(len(resolve_ledger_key(self.key)), 32)


if __name__ == "__main__":
    unittest.main()
