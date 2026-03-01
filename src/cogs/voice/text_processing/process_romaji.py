# src/cogs/voice/text_processing/process_romaji.py
import romkan2


def process_romaji(content: str) -> str:
    return romkan2.to_hiragana(content)
