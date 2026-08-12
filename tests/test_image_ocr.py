import unittest

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
