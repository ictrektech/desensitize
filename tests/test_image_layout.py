import unittest

from app.services.image_layout import OcrBlock, Point, Rect, rebuild_text
from app.services.image_matcher import match_rebuilt_text
from app.services.rule_store import rule_store


def block(text: str, x1: float, y1: float, x2: float, y2: float) -> OcrBlock:
    return OcrBlock(
        text=text,
        quad=[
            Point(x1, y1),
            Point(x2, y1),
            Point(x2, y2),
            Point(x1, y2),
        ],
        bbox=Rect(x1, y1, x2, y2),
        score=0.99,
    )


class ImageLayoutMatchingTest(unittest.TestCase):
    def setUp(self) -> None:
        rule_store.reload()

    def test_split_phone_number_matches_compact_text_and_maps_all_boxes(self) -> None:
        rebuilt = rebuild_text(
            [
                block("我的手机号是", 10, 10, 90, 30),
                block("138123", 95, 10, 145, 30),
                block("45678", 150, 10, 195, 30),
            ]
        )

        matches = match_rebuilt_text(rebuilt, ["phone_cn"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].placeholder, "[PHONE_NUMBER]")
        self.assertEqual(matches[0].block_ids, [1, 2])
        self.assertEqual(rebuilt.block_ranges[1], (7, 13))

    def test_split_openai_key_matches_compact_text(self) -> None:
        rebuilt = rebuild_text(
            [
                block("密钥", 10, 10, 45, 30),
                block("sk-live-abc123def456", 50, 10, 190, 30),
                block("ghi789jkl012mno345pqr", 195, 10, 350, 30),
            ]
        )

        matches = match_rebuilt_text(rebuilt, ["api_key_openai"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].placeholder, "[API_KEY]")
        self.assertEqual(matches[0].block_ids, [1, 2])

    def test_reverse_confusion_space_for_api_key_literals(self) -> None:
        rebuilt = rebuild_text([block("sk-l1ve-abc123def456ghi789jkl012mno345pqr", 10, 10, 420, 30)])

        matches = match_rebuilt_text(rebuilt, ["api_key_openai"])

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].matched_via, "reverse_confused")


if __name__ == "__main__":
    unittest.main()
