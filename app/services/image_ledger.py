"""Reversible redaction ledger.

Before masking, each region's original pixels are cropped, PNG-serialized and
sealed with AES-256-GCM under a caller-supplied 32-byte key (one random nonce
per region). The resulting ledger travels with the masked image; only key
holders can restore the covered content.
"""

from __future__ import annotations

import base64
import io
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image

from app.services.image_masker import MaskRegion, decode_image_base64

LEDGER_VERSION = 1
LEDGER_ALG = "AES-256-GCM"


def resolve_ledger_key(ledger_key: str | None) -> bytes:
    key = ledger_key or os.getenv("DESENSITIZE_LEDGER_KEY")
    if not key:
        raise ValueError("可逆脱敏需要 ledger_key 或环境变量 DESENSITIZE_LEDGER_KEY")
    try:
        raw = bytes.fromhex(key)
    except ValueError as exc:
        raise ValueError("ledger_key 必须是 64 位 hex 字符串（32 字节）") from exc
    if len(raw) != 32:
        raise ValueError("ledger_key 必须是 64 位 hex 字符串（32 字节）")
    return raw


def _clamped_box(box, image: Image.Image) -> tuple[int, int, int, int] | None:
    width, height = image.size
    # One extra pixel per side: polygon fills are edge-inclusive, so the crop
    # must fully cover every blackened pixel for an exact restore.
    x1 = max(0, int(round(box.x1)) - 1)
    y1 = max(0, int(round(box.y1)) - 1)
    x2 = min(width, int(round(box.x2)) + 1)
    y2 = min(height, int(round(box.y2)) + 1)
    if x2 <= x1 or y2 <= y1:
        return None
    return (x1, y1, x2, y2)


def build_ledger(image: Image.Image, regions: list[MaskRegion], key: bytes) -> dict:
    aes = AESGCM(key)
    entries: list[dict] = []
    for index, region in enumerate(regions):
        box = _clamped_box(region.box, image)
        if box is None:
            continue
        crop = image.crop(box)
        buffer = io.BytesIO()
        crop.save(buffer, format="PNG")
        nonce = os.urandom(12)
        ciphertext = aes.encrypt(nonce, buffer.getvalue(), str(index).encode("ascii"))
        entries.append(
            {
                "index": index,
                "box": {"x1": box[0], "y1": box[1], "x2": box[2], "y2": box[3]},
                "nonce": base64.b64encode(nonce).decode("ascii"),
                "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
            }
        )
    return {"version": LEDGER_VERSION, "alg": LEDGER_ALG, "region_count": len(entries), "regions": entries}


def restore_image(masked_base64: str, ledger: dict, key: bytes) -> tuple[Image.Image, list[dict]]:
    image = decode_image_base64(masked_base64)
    aes = AESGCM(key)
    report: list[dict] = []
    for entry in ledger.get("regions", []):
        index = entry.get("index")
        item: dict = {"index": index, "restored": False}
        try:
            nonce = base64.b64decode(entry["nonce"])
            ciphertext = base64.b64decode(entry["ciphertext"])
            payload = aes.decrypt(nonce, ciphertext, str(index).encode("ascii"))
            crop = Image.open(io.BytesIO(payload)).convert("RGB")
            box = entry["box"]
            x1, y1 = int(box["x1"]), int(box["y1"])
            x2, y2 = int(box["x2"]), int(box["y2"])
            width, height = image.size
            if 0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height:
                if crop.size != (x2 - x1, y2 - y1):
                    crop = crop.resize((x2 - x1, y2 - y1))
                image.paste(crop, (x1, y1))
                item["restored"] = True
            else:
                item["error"] = "region outside image bounds"
        except InvalidTag:
            item["error"] = "decrypt failed: wrong key or tampered data"
        except Exception as exc:  # malformed entry never aborts the whole restore
            item["error"] = f"restore failed: {exc}"
        report.append(item)
    return image, report
