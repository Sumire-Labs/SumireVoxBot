# src/cogs/voice/handlers/on_voice_state_update_auto_join.py
import asyncio
import discord
from loguru import logger

from ..session.save_voice_session import save_voice_session
from ..dictionary.load_guild_dict import load_guild_dict
from ..embeds.create_auto_join_embed import create_auto_join_embed


async def on_voice_state_update_auto_join(
    bot,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
    read_channels: dict
) -> None:
    if member.bot or before.channel == after.channel or after.channel is None:
        return

    guild_id = member.guild.id

    try:
        is_active = await bot.db.is_instance_active(guild_id)
        if not is_active:
            return

        settings = await bot.db.get_guild_settings(guild_id)
    except Exception as e:
        logger.error(f"[{guild_id}] 自動接続設定取得失敗: {e}")
        return

    if not settings.auto_join:
        return

    bot_key = str(bot.user.id)
    if bot_key not in settings.auto_join_config:
        return

    config = settings.auto_join_config[bot_key]
    target_vc_id = config.get("voice")
    target_tc_id = config.get("text")

    if after.channel.id != target_vc_id or member.guild.voice_client:
        return

    try:
        await after.channel.connect()
        read_channels[guild_id] = target_tc_id

        logger.success(f"[{guild_id}] 自動接続成功: {after.channel.name}")

        asyncio.create_task(load_guild_dict(bot, guild_id))
        asyncio.create_task(save_voice_session(bot, guild_id, after.channel.id, target_tc_id))

        tc = member.guild.get_channel(target_tc_id)
        if tc:
            embed = create_auto_join_embed(after.channel.name)
            await tc.send(embed=embed)

    except Exception as e:
        logger.error(f"[{guild_id}] 自動接続失敗: {e}")
