# src/cogs/voice/validators/is_skip_command.py
def is_skip_command(content: str) -> bool:
    return content.strip() in ("s", "ｓ")
