# src/cogs/voice/validators/is_ignored_prefix.py
def is_ignored_prefix(content: str) -> bool:
    return content.startswith(("!", "！"))
