# src/cogs/voice/text_processing/truncate_text.py
def truncate_text(content: str, max_chars: int) -> str:
    if len(content) > max_chars:
        return content[:max_chars] + "、以下略"
    return content
