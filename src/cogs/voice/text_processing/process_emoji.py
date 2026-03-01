# src/cogs/voice/text_processing/process_emoji.py
import emoji


def process_emoji(content: str, read_emoji: bool) -> str:
    if read_emoji:
        content = emoji.demojize(content, language="ja")
        content = content.replace(":", "、")
    else:
        content = emoji.replace_emoji(content, "")
    return content
