# src/cogs/voice/formatters/format_rendered_datetime.py
import re


def format_rendered_datetime(match: re.Match) -> str:
    y = int(match.group("y"))
    mo = int(match.group("mo"))
    d = int(match.group("d"))
    hh = int(match.group("hh"))
    mm = int(match.group("mm"))
    ss = int(match.group("ss"))
    return f"{y}年{mo}月{d}日{hh}時{mm}分{ss}秒"
