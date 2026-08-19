import unittest

from app.services.image_layout import OcrBlock, Point, Rect, rebuild_text
from app.services.image_matcher import match_rebuilt_text, match_rebuilt_text_with_audit
from app.services.rule_store import rule_store


def block(text, x1, y1, x2, y2):
    quad = [Point(x1, y1), Point(x2, y1), Point(x2, y2), Point(x1, y2)]
    return OcrBlock(text=text, quad=quad, bbox=Rect(x1, y1, x2, y2), score=0.99)


class ConfusionMatchingTest(unittest.TestCase):
    def setUp(self):
        rule_store.reload()

    def test_confused_phone_hits_across_blocks(self):
        rebuilt = rebuild_text(
            [
                block("l38", 10, 10, 60, 50),
                block("OOl3", 70, 10, 140, 50),
                block("8000", 150, 10, 210, 50),
            ]
        )
        self.assertEqual(rebuilt.confused_text, "13800138000")
        matches = match_rebuilt_text(rebuilt, ["phone_cn"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].rule_id, "phone_cn")
        self.assertEqual(matches[0].matched_via, "confused")
        self.assertEqual(matches[0].block_ids, [0, 1, 2])

    def test_pure_digit_split_hits_compact_not_confused(self):
        rebuilt = rebuild_text(
            [
                block("138", 10, 10, 60, 50),
                block("0013", 70, 10, 140, 50),
                block("8000", 150, 10, 210, 50),
            ]
        )
        self.assertEqual(rebuilt.confused_text, rebuilt.compact_text)
        matches = match_rebuilt_text(rebuilt, ["phone_cn"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_via, "compact")

    def test_confused_id_card_valid_checksum(self):
        rebuilt = rebuild_text([block("llO10519491231002X", 10, 10, 320, 50)])
        self.assertEqual(rebuilt.confused_text, "11010519491231002X")
        matches = match_rebuilt_text(rebuilt, ["id_card_cn"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_via, "confused")
        self.assertEqual(matches[0].placeholder, "[ID_CARD]")

    def test_confused_id_card_bad_checksum_dropped(self):
        rebuilt = rebuild_text([block("llO10519491231002l", 10, 10, 320, 50)])
        self.assertEqual(rebuilt.confused_text, "110105194912310021")
        result = match_rebuilt_text_with_audit(rebuilt, ["id_card_cn"])
        self.assertEqual(result.matches, [])
        self.assertEqual(len(result.audit.rejected_candidates), 1)
        self.assertEqual(result.audit.rejected_candidates[0].reason, "validator_failed")

    def test_text_space_match_untouched_by_validator(self):
        # Digit-perfect values keep matching in the text space; the checksum
        # gate only applies to the confusion-normalized pass.
        rebuilt = rebuild_text([block("no 123456789012345678 here", 10, 10, 420, 50)])
        matches = match_rebuilt_text(rebuilt, ["id_card_cn"])
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_via, "text")

    def test_suppressed_space_is_counted(self):
        rebuilt = rebuild_text([block("4111111111111111", 10, 10, 260, 50)])
        result = match_rebuilt_text_with_audit(rebuilt, ["bank_card", "cn_taxpayer_id"])
        self.assertEqual(len(result.matches), 1)
        self.assertGreaterEqual(result.audit.suppressed_by_space.get("text", 0), 1)


if __name__ == "__main__":
    unittest.main()
