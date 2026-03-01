# src/cogs/voice/text_processing/process_rendered_datetime.py
import re

from ..formatters.format_rendered_datetime import format_rendered_datetime


def process_rendered_datetime(content: str) -> str:
    return re.sub(
        r"(?P<y>\d{4})/(?P<mo>\d{2})/(?P<d>\d{2})[ ](?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})",
        format_rendered_datetime,
        content
    )
