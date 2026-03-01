# src/cogs/voice/queue/get_queue.py
import asyncio


def get_queue(queues: dict, is_processing: dict, guild_id: int) -> asyncio.Queue:
    if guild_id not in queues:
        queues[guild_id] = asyncio.Queue()
        is_processing[guild_id] = False
    return queues[guild_id]
