# src/cogs/voice/queue/is_processing.py
def is_processing(processing_dict: dict, guild_id: int) -> bool:
    return processing_dict.get(guild_id, False)
