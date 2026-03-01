# src/cogs/voice/audio/enqueue_message.py
import asyncio
import uuid
from loguru import logger

from ..models.audio_task import AudioTask
from ..queue.get_queue import get_queue
from ..queue.is_processing import is_processing
from .generate_audio import generate_audio
from .play_next import play_next


async def enqueue_message(
    bot,
    queues: dict,
    processing_dict: dict,
    temp_dir: str,
    guild_id: int,
    text: str,
    author_id: int
) -> None:
    task_id = str(uuid.uuid4())
    file_path = f"{temp_dir}/audio_{guild_id}_{task_id}.wav"

    audio_task = AudioTask(
        task_id=task_id,
        text=text,
        author_id=author_id,
        file_path=file_path
    )

    audio_task.generation_task = asyncio.create_task(
        generate_audio(bot, audio_task, guild_id)
    )

    queue = get_queue(queues, processing_dict, guild_id)
    await queue.put(audio_task)

    logger.debug(f"[{guild_id}] キューに追加 ({task_id}): {text[:20]}...")

    if not is_processing(processing_dict, guild_id):
        asyncio.create_task(play_next(bot, queues, processing_dict, guild_id))
