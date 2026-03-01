# src/cogs/voice/handlers/on_voice_state_update_clear_on_leave.py
import asyncio
import discord
from loguru import logger

from ..constants.timeouts import DISCONNECT_CONFIRM_DELAY
from ..session.is_reconnected import is_reconnected
from ..session.delete_session_background import delete_session_background
from ..queue.clear_queue import clear_queue
from ..helpers.cancel_generation_task import cancel_generation_task
from ..helpers.delete_audio_file import delete_audio_file


async def on_voice_state_update_clear_on_leave(
    bot,
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
    read_channels: dict,
    queues: dict,
    is_processing: dict
) -> None:
    # Bot自身の切断でなければ無視
    if member.id != bot.user.id or before.channel is None or after.channel is not None:
        return

    guild_id = member.guild.id

    try:
        logger.info(f"[{guild_id}] VC切断検知。{DISCONNECT_CONFIRM_DELAY}秒後に再確認...")
        await asyncio.sleep(DISCONNECT_CONFIRM_DELAY)

        if is_reconnected(bot, guild_id):
            logger.info(f"[{guild_id}] 再接続確認。クリアをスキップ")
            return

        logger.warning(f"[{guild_id}] VC切断確認。キューをクリア")

        read_channels.pop(guild_id, None)
        await bot.db.unload_guild_dict(guild_id)

        cleared_tasks = await clear_queue(queues, is_processing, guild_id)
        for task in cleared_tasks:
            await cancel_generation_task(task, guild_id)
            delete_audio_file(task, guild_id)

        asyncio.create_task(delete_session_background(bot, guild_id))

    except asyncio.CancelledError:
        logger.warning(f"[{guild_id}] クリーンアップがキャンセル")
        raise
    except Exception as e:
        logger.error(f"[{guild_id}] クリーンアップエラー: {e}")
