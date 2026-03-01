# src/cogs/voice/audio/normalize_text.py
import jaconv


def normalize_text(text: str) -> str:
    return jaconv.h2z(text, kana=True, digit=True, ascii=True).lower()
