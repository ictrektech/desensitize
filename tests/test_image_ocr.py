import unittest
import base64
import io
from unittest.mock import patch

from PIL import Image
from app.services.image_masker import decode_image_base64
from app.services import scheduler

from app.services.image_ocr import (
    _rapidocr_active_providers,
    _rapidocr_provider_kwargs,
    _rapidocr_uses_cuda,
)


class FakeSession:
    def __init__(self, providers):
        self._providers = providers

    def get_providers(self):
        return self._providers


class EncodedInputBoundaryTests(unittest.TestCase):
    def test_base64_padding_does_not_reject_exact_calibrated_byte_limit(self):
        stream = io.BytesIO()
        Image.new('RGB', (1, 1), 'white').save(stream, format='PNG')
        for remainder in [1, 2]:
            raw = stream.getvalue()
            raw += b'x' * ((remainder - len(raw)) % 3)
            encoded = base64.b64encode(raw).decode()
            def check(model, metrics):
                if 'input_bytes' in metrics:
                    self.assertLessEqual(metrics['input_bytes'], len(raw))
            with patch.object(scheduler, 'validate_limits', side_effect=check) as validate:
                decoded = decode_image_base64(encoded, scheduled_model='ocr')
            self.assertEqual(decoded.size, (1, 1))
            self.assertEqual(validate.call_args_list[0].args[1]['input_bytes'], len(raw))


class FakeInfer:
    def __init__(self, providers):
        self.session = FakeSession(providers)


class FakeOcrPart:
    def __init__(self, attr, providers):
        setattr(self, attr, FakeInfer(providers))


class FakeRapidOcr:
    def __init__(self, providers):
        self.text_det = FakeOcrPart("infer", providers)
        self.text_cls = FakeOcrPart("infer", providers)
        self.text_rec = FakeOcrPart("session", providers)


class ImageOcrProviderTest(unittest.TestCase):
    def test_cuda_provider_uses_rapidocr_cuda_flags(self) -> None:
        self.assertEqual(
            _rapidocr_provider_kwargs("cuda"),
            {"det_use_cuda": True, "rec_use_cuda": True, "cls_use_cuda": True},
        )

    def test_cpu_provider_disables_rapidocr_cuda_flags(self) -> None:
        self.assertEqual(
            _rapidocr_provider_kwargs("cpu"),
            {"det_use_cuda": False, "rec_use_cuda": False, "cls_use_cuda": False},
        )

    def test_reads_active_providers_from_all_rapidocr_sessions(self) -> None:
        active = _rapidocr_active_providers(FakeRapidOcr(["CUDAExecutionProvider", "CPUExecutionProvider"]))

        self.assertEqual(
            active,
            {
                "det": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                "cls": ["CUDAExecutionProvider", "CPUExecutionProvider"],
                "rec": ["CUDAExecutionProvider", "CPUExecutionProvider"],
            },
        )
        self.assertTrue(_rapidocr_uses_cuda(active))

    def test_detects_cpu_fallback(self) -> None:
        active = _rapidocr_active_providers(FakeRapidOcr(["CPUExecutionProvider"]))

        self.assertFalse(_rapidocr_uses_cuda(active))


if __name__ == "__main__":
    unittest.main()
