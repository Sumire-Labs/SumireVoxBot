# src/cogs/voice/text_processing/skip_urls.py
import re


def skip_urls(content: str) -> str:
    return re.sub(r"https?://[\w/:%#$&?()~.=+\-]+", "、ユーアールエル省略、", content)
