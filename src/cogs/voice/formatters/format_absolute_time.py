# src/cogs/voice/formatters/format_absolute_time.py
from datetime import datetime


def format_absolute_time(dt: datetime, fmt: str) -> str:
    local_dt = dt.astimezone()
    y, mo, d = local_dt.year, local_dt.month, local_dt.day
    h, m, s = local_dt.hour, local_dt.minute, local_dt.second

    formats = {
        "t": f"{h}時{m}分",
        "T": f"{h}時{m}分{s}秒",
        "d": f"{y}年{mo}月{d}日",
        "D": f"{y}年{mo}月{d}日",
        "f": f"{y}年{mo}月{d}日{h}時{m}分",
        "F": f"{y}年{mo}月{d}日{h}時{m}分",
        "S": f"{y}年{mo}月{d}日{h}時{m}分{s}秒",
    }
    return formats.get(fmt, f"{y}年{mo}月{d}日{h}時{m}分")
