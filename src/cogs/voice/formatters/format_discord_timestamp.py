# src/cogs/voice/formatters/format_discord_timestamp.py
import re
from datetime import datetime, timezone

from .format_relative_time import format_relative_time
from .format_absolute_time import format_absolute_time


def format_discord_timestamp(match: re.Match) -> str:
    try:
        unix = int(match.group("unix"))
    except Exception:
        return match.group(0)

    fmt = match.group("fmt") or "f"
    dt = datetime.fromtimestamp(unix, tz=timezone.utc)

    if fmt == "R":
        return format_relative_time(dt)

    return format_absolute_time(dt, fmt)
