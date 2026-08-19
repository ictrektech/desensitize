"""Checksum validators that gate matches made in the confusion-normalized space.

Pure functions so they can be unit-tested and reused by future rule types.
"""

from __future__ import annotations

import re

# GB 11643 mod 11-2 checksum for 18-digit resident ID numbers.
_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_ID_CHECK_CHARS = "10X98765432"

_MOBILE_RE = re.compile(r"1[3-9]\d{9}")
_IBAN_RE = re.compile(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}")
_VIN_RE = re.compile(r"[A-HJ-NPR-Z0-9]{17}")
_VIN_TRANSLITERATION = {
    **{str(i): i for i in range(10)},
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5,
    "F": 6,
    "G": 7,
    "H": 8,
    "J": 1,
    "K": 2,
    "L": 3,
    "M": 4,
    "N": 5,
    "P": 7,
    "R": 9,
    "S": 2,
    "T": 3,
    "U": 4,
    "V": 5,
    "W": 6,
    "X": 7,
    "Y": 8,
    "Z": 9,
}
_VIN_WEIGHTS = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)


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


def iban_mod97(value: str) -> bool:
    value = re.sub(r"\s+", "", value or "").upper()
    if not _IBAN_RE.fullmatch(value):
        return False
    rotated = value[4:] + value[:4]
    digits = []
    for ch in rotated:
        if ch.isdigit():
            digits.append(ch)
        elif "A" <= ch <= "Z":
            digits.append(str(ord(ch) - ord("A") + 10))
        else:
            return False
    remainder = 0
    for ch in "".join(digits):
        remainder = (remainder * 10 + int(ch)) % 97
    return remainder == 1


def vin_iso3779(value: str) -> bool:
    value = re.sub(r"\s+", "", value or "").upper()
    if not _VIN_RE.fullmatch(value):
        return False
    total = 0
    for ch, weight in zip(value, _VIN_WEIGHTS):
        total += _VIN_TRANSLITERATION[ch] * weight
    expected = total % 11
    check = "X" if expected == 10 else str(expected)
    return value[8] == check


VALIDATORS = {
    "china_id": china_id_checksum,
    "luhn": luhn_valid,
    "cn_mobile": cn_mobile,
    "iban": iban_mod97,
    "vin": vin_iso3779,
}
