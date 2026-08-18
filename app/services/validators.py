"""Checksum validators that gate matches made in the confusion-normalized space.

Pure functions so they can be unit-tested and reused by future rule types.
"""

from __future__ import annotations

import re

# GB 11643 mod 11-2 checksum for 18-digit resident ID numbers.
_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK_CHARS = "10X98765432"

_MOBILE_RE = re.compile(r"1[3-9]\d{9}")


def china_id_checksum(value: str) -> bool:
    value = value.strip().upper()
    if len(value) != 18 or not value[:17].isdigit() or value[17] not in "0123456789X":
        return False
    total = sum(int(d) * w for d, w in zip(value[:17], _ID_WEIGHTS))
    return _ID_CHECK_CHARS[total % 11] == value[17]


def luhn_valid(value: str) -> bool:
    value = value.strip()
    if not value.isdigit() or len(value) < 2:
        return False
    total = 0
    for i, ch in enumerate(reversed(value)):
        digit = int(ch)
        if i % 2 == 1:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def cn_mobile(value: str) -> bool:
    value = value.strip()
    if value.startswith("+86"):
        value = value[3:]
    elif value.startswith("86") and len(value) == 13:
        value = value[2:]
    return _MOBILE_RE.fullmatch(value) is not None


VALIDATORS = {
    "china_id": china_id_checksum,
    "luhn": luhn_valid,
    "cn_mobile": cn_mobile,
}
