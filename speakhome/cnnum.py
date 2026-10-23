"""Parse Chinese and Arabic numbers as they are spoken in Mandarin.

Handles colloquial forms that older speakers use all the time, for example
"一百五" (150, not 105), "一百零五" (105), "兩百" (200) and "十五" (15).
"""
from __future__ import annotations

import re
import unicodedata

DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4,
          "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNITS = {"十": 10, "百": 100, "千": 1000}

CN_CHARS = "零〇一二兩两三四五六七八九十百千"
# One number token: Arabic digits (optionally decimal) or a run of Chinese numerals.
NUM = rf"(?:[0-9]+(?:\.[0-9]+)?|[{CN_CHARS}]+)"
NOT_NUM = rf"[^0-9{CN_CHARS}]"


def normalize(text: str) -> str:
    """Full-width digits and punctuation to half-width; keeps the Chinese text."""
    return unicodedata.normalize("NFKC", text)


def cn2num(token: str) -> float | None:
    """Convert one number token to a number. Returns None if it is not a number."""
    token = normalize(token).strip()
    if not token:
        return None
    if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", token):
        return float(token) if "." in token else int(token)
    if any(ch not in DIGITS and ch not in UNITS for ch in token):
        return None

    total = 0
    num = 0
    last_unit = 1
    zero_after_unit = False
    for ch in token:
        if ch in DIGITS:
            if DIGITS[ch] == 0:
                zero_after_unit = True
                num = 0
            else:
                num = DIGITS[ch]
        else:  # unit
            unit = UNITS[ch]
            if num == 0 and unit == 10:
                num = 1  # "十五" = 15
            total += num * unit
            num = 0
            last_unit = unit
            zero_after_unit = False
    if num:
        # Colloquial shorthand: "一百五" = 150, "兩千三" = 2300,
        # unless a zero sits in between ("一百零五" = 105).
        if last_unit >= 100 and not zero_after_unit:
            total += num * (last_unit // 10)
        else:
            total += num
    return total


def numbers_in(text: str) -> set[float]:
    """Every number mentioned in a text, used to check that values are grounded."""
    text = normalize(text)
    found = set()
    for tok in re.findall(NUM, text):
        value = cn2num(tok)
        if value is not None:
            found.add(value)
    return found
