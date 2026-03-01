# src/cogs/voice/handlers/on_voice_state_update_notification.py
import discord
from loguru import logger

from ..audio.enqueue_message import enqueue_message


async def on_voice_state_update_notification(
    bot,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
    queues: dict,
    is_processing: dict,
    temp_dir: str
) -> None:
    if member.bot or not member.guild.voice_client:
        return

    bot_vc = member.guild.voice_client.channel
    guild_id = member.guild.id

    try:
        settings = await bot.db.get_guild_settings(guild_id)
    except Exception as e:
        logger.error(f"[{guild_id}] サーバー設定取得失敗: {e}")
        return

    if not settings.read_vc_status:
        return

    content = None
    suffix = "さん" if settings.add_suffix else ""

    if before.channel != bot_vc and after.channel == bot_vc:
        content = f"{member.display_name}{suffix}が入室しました"
    elif before.channel == bot_vc and after.channel != bot_vc:
        content = f"{member.display_name}{suffix}が退室しました"

    if content:
        await enqueue_message(bot, queues, is_processing, temp_dir, guild_id, content, member.id)
