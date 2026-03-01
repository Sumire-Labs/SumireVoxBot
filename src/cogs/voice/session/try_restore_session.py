# src/cogs/voice/session/try_restore_session.py
import asyncio
import discord
from loguru import logger

from ..helpers.check_other_bot_in_channel import check_other_bot_in_channel
from ..helpers.check_voice_permissions import check_voice_permissions
from ..helpers.get_human_members import get_human_members
from ..embeds.create_reconnect_embed import create_reconnect_embed


async def try_restore_session(
    bot,
    read_channels: dict,
    guild_id: int,
    voice_channel_id: int,
    text_channel_id: int
) -> bool:
    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.warning(f"[{guild_id}] 復元スキップ: ギルドが見つかりません")
            return False

        voice_channel = guild.get_channel(voice_channel_id)
        if not voice_channel or not isinstance(voice_channel, (discord.VoiceChannel, discord.StageChannel)):
            logger.warning(f"[{guild_id}] 復元スキップ: VCが見つかりません")
            return False

        text_channel = guild.get_channel(text_channel_id)
        if not text_channel or not isinstance(text_channel, discord.TextChannel):
            logger.warning(f"[{guild_id}] 復元スキップ: TCが見つかりません")
            return False

        if not get_human_members(voice_channel):
            logger.info(f"[{guild_id}] 復元スキップ: VCに人がいません")
            return False

        if guild.voice_client and guild.voice_client.is_connected():
            read_channels[guild_id] = text_channel_id
            await bot.db.load_guild_dict(guild_id)
            return True

        if check_other_bot_in_channel(voice_channel, bot.user.id):
            logger.info(f"[{guild_id}] 復元スキップ: 他のBotが存在")
            return False

        if not check_voice_permissions(voice_channel, guild):
            logger.warning(f"[{guild_id}] 復元スキップ: 権限不足")
            return False

        try:
            await voice_channel.connect(timeout=10.0)
        except (asyncio.TimeoutError, discord.errors.ClientException) as e:
            logger.warning(f"[{guild_id}] 復元失敗: {e}")
            return False

        read_channels[guild_id] = text_channel_id
        await bot.db.load_guild_dict(guild_id)

        logger.success(f"[{guild_id}] セッション復元: VC={voice_channel.name}")

        try:
            embed = create_reconnect_embed(voice_channel.name)
            await text_channel.send(embed=embed)
        except Exception as e:
            logger.warning(f"[{guild_id}] 復元通知送信失敗: {e}")

        return True

    except Exception as e:
        logger.error(f"[{guild_id}] 復元中に予期しないエラー: {e}")
        return False
