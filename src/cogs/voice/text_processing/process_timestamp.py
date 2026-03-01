# src/cogs/voice/text_processing/process_timestamp.py
import re

from ..formatters.format_discord_timestamp import format_discord_timestamp


def process_timestamp(content: str) -> str:
    return re.sub(
        r"<t:(?P<unix>\d+)(?::(?P<fmt>[A-Za-z]))?>",
        format_discord_timestamp,
        content
    )
