# src/cogs/voice/session/is_reconnected.py
def is_reconnected(bot, guild_id: int) -> bool:
    guild = bot.get_guild(guild_id)
    vc = guild.voice_client if guild else None
    return bool(vc and vc.is_connected())
