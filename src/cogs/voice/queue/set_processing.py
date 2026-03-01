# src/cogs/voice/queue/set_processing.py
def set_processing(processing_dict: dict, guild_id: int, value: bool) -> None:
    processing_dict[guild_id] = value
