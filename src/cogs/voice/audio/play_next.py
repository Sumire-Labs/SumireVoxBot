# src/cogs/voice/audio/play_next.py
from loguru import logger

from ..queue.get_queue import get_queue
from ..queue.set_processing import set_processing
from .play_audio_task import play_audio_task
from .cleanup_audio_file import cleanup_audio_file


async def play_next(bot, queues: dict, is_processing: dict, guild_id: int) -> None:
    set_processing(is_processing, guild_id, True)
    queue = get_queue(queues, is_processing, guild_id)
    guild = bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)

    logger.debug(f"[{guild_id}] play_next開始, queue_size={queue.qsize()}")

    try:
        while not queue.empty():
            audio_task = await queue.get()
            try:
                await play_audio_task(bot, guild, audio_task)
            except Exception as e:
                logger.error(f"[{guild_id}] 再生中エラー: {e}")
            finally:
                queue.task_done()
                await cleanup_audio_file(audio_task.file_path, guild_id)
    finally:
        set_processing(is_processing, guild_id, False)
