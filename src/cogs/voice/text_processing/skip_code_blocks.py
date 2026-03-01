# src/cogs/voice/text_processing/skip_code_blocks.py
import re


def skip_code_blocks(content: str) -> str:
    content = re.sub(r"```.*?```", "、コードブロック省略、", content, flags=re.DOTALL)
    content = re.sub(r"`.*?`", "、コード省略、", content, flags=re.DOTALL)
    return content
