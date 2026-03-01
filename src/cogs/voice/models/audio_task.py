# src/cogs/voice/models/audio_task.py
import asyncio
from dataclasses import dataclass, field


@dataclass
class AudioTask:
    task_id: str
    text: str
    author_id: int
    file_path: str
    generation_task: asyncio.Task = field(default=None, repr=False)
    is_ready: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    is_failed: bool = False
