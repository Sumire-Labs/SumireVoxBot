# src/cogs/voice/handlers/on_voice_state_update_auto_leave.py
import asyncio
import discord
from loguru import logger

from ..constants.intervals import AUTO_LEAVE_INTERVAL
from ..helpers.get_human_members import get_human_members
from ..session.delete_session_background import delete_session_background
from ..dictionary.load_guild_dict import load_guild_dict


async def on_voice_state_update_auto_leave(
    bot,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
    read_channels: dict
) -> None:
    if before.channel is None or before.channel == after.channel:
        return

    vc = member.guild.voice_client
    if not vc:
        return

    if before.channel.id != vc.channel.id:
        return

    await asyncio.sleep(AUTO_LEAVE_INTERVAL)

    if get_human_members(vc.channel):
        return

    guild_id = member.guild.id
    logger.info(f"[{guild_id}] 自動切断: {vc.channel.name}")

    read_channels.pop(guild_id, None)
    await vc.disconnect(force=True)

    asyncio.create_task(bot.db.unload_guild_dict(guild_id))
    asyncio.create_task(delete_session_background(bot, guild_id))
