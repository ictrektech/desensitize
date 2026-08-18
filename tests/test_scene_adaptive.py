import unittest

from app.services.image_layout import OcrBlock, Point, Rect
from app.services.image_scene import classify_scene, effective_rule_ids
from app.services.rule_store import rule_store


def block(text, x1, y1, x2, y2):
    quad = [Point(x1, y1), Point(x2, y1), Point(x2, y2), Point(x1, y2)]
    return OcrBlock(text=text, quad=quad, bbox=Rect(x1, y1, x2, y2), score=0.99)


class SceneClassifyTest(unittest.TestCase):
    def test_invoice(self):
        blocks = [
            block("增值税电子普通发票", 10, 10, 300, 50),
            block("价税合计（大写）叁佰元", 10, 70, 320, 110),
            block("统一社会信用代码91110108MA01B1234X", 10, 130, 480, 170),
        ]
        scene = classify_scene(blocks)
        self.assertEqual(scene["type"], "invoice")
        self.assertTrue(scene["policy"]["field_fallback"])
        self.assertIsNone(scene["policy"]["rule_categories"])

    def test_config_screenshot_narrows_rules(self):
        blocks = [
            block("api_key=sk-abc123defg456", 10, 10, 300, 50),
            block("token: ghp_16C7e42F292cT", 10, 70, 320, 110),
            block("https://api.example.com/v1", 10, 130, 340, 170),
        ]
        scene = classify_scene(blocks)
        self.assertEqual(scene["type"], "config_screenshot")
        self.assertEqual(scene["policy"]["rule_categories"], ["api_key", "pii"])
        self.assertFalse(scene["policy"]["field_fallback"])

        ids = effective_rule_ids(scene, None)
        self.assertIn("api_key_openai", ids)
        self.assertIn("phone_cn", ids)
        self.assertNotIn("cn_invoice_number", ids)
        self.assertNotIn("cn_logistics_order", ids)

        selected = effective_rule_ids(scene, ["cn_invoice_number", "phone_cn"])
        self.assertEqual(selected, ["phone_cn"])

    def test_generic_when_weak_or_tied_signals(self):
        single = classify_scene([block("发票抬头", 10, 10, 120, 50)])
        self.assertEqual(single["type"], "generic")
        tied = classify_scene(
            [block("发票代码", 10, 10, 160, 50), block("token: abc123", 10, 70, 260, 110)]
        )
        self.assertEqual(tied["type"], "generic")

    def test_generic_policy_keeps_everything(self):
        scene = classify_scene([])
        self.assertEqual(scene["type"], "generic")
        self.assertEqual(effective_rule_ids(scene, ["phone_cn"]), ["phone_cn"])
        self.assertEqual(effective_rule_ids(None, None), None)


if __name__ == "__main__":
    unittest.main()
