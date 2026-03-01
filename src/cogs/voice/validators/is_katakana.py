# src/cogs/voice/validators/is_katakana.py
import re


def is_katakana(text: str) -> bool:
    return re.fullmatch(r'^[ァ-ヶーヴ]+$', text) is not None
