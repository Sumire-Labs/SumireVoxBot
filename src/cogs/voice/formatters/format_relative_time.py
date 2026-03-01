# src/cogs/voice/formatters/format_relative_time.py
from datetime import datetime, timezone


def format_relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    delta_sec = int((dt - now).total_seconds())
    future = delta_sec > 0
    sec = abs(delta_sec)

    if sec < 60:
        n, unit = sec, "秒"
    elif sec < 3600:
        n, unit = sec // 60, "分"
    elif sec < 86400:
        n, unit = sec // 3600, "時間"
    elif sec < 86400 * 30:
        n, unit = sec // 86400, "日"
    elif sec < 86400 * 365:
        n, unit = sec // (86400 * 30), "か月"
    else:
        n, unit = sec // (86400 * 365), "年"

    return f"{max(1, n)}{unit}{'後' if future else '前'}"
