# src/cogs/voice/queue/clear_queue.py
import asyncio
from loguru import logger


async def clear_queue(queues: dict, is_processing: dict, guild_id: int) -> list:
    if guild_id not in queues:
        return []

    queue = queues[guild_id]
    cleared_tasks = []

    while True:
        try:
            task = queue.get_nowait()
            cleared_tasks.append(task)
        except asyncio.QueueEmpty:
            break

    del queues[guild_id]
    is_processing.pop(guild_id, None)

    logger.debug(f"[{guild_id}] キューをクリア: {len(cleared_tasks)}件")
    return cleared_tasks
