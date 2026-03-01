# src/cogs/voice/text_processing/process_custom_emoji.py
import re


def process_custom_emoji(content: str) -> str:
    return re.sub(r"<a?:(\w+):?\d+>", r"\1", content)
