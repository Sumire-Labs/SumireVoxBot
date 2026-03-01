# src/cogs/voice/helpers/cancel_generation_task.py
import asyncio
from loguru import logger

from ..models.audio_task import AudioTask


async def cancel_generation_task(audio_task: AudioTask, guild_id: int) -> None:
    task = audio_task.generation_task
    if not task or task.done():
        return

    try:
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
    except Exception as e:
        logger.error(f"[{guild_id}] タスクキャンセルエラー: {e}")
