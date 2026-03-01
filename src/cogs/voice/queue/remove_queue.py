# src/cogs/voice/queue/remove_queue.py
def remove_queue(queues: dict, is_processing: dict, guild_id: int) -> None:
    queues.pop(guild_id, None)
    is_processing.pop(guild_id, None)
