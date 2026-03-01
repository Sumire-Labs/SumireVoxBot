# src/cogs/voice/audio/play_audio_task.py
import os
import asyncio
import discord
from loguru import logger

from ..models.audio_task import AudioTask
from ..constants.timeouts import AUDIO_GENERATION_TIMEOUT, PLAYBACK_TIMEOUT


async def play_audio_task(bot, guild, audio_task: AudioTask) -> None:
    guild_id = guild.id

    try:
        await asyncio.wait_for(audio_task.is_ready.wait(), timeout=AUDIO_GENERATION_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning(f"[{guild_id}] 音声生成タイムアウト ({audio_task.task_id})")
        return

    if audio_task.is_failed:
        logger.warning(f"[{guild_id}] 音声生成失敗のためスキップ ({audio_task.task_id})")
        return

    if not os.path.exists(audio_task.file_path):
        logger.error(f"[{guild_id}] ファイルが見つかりません: {audio_task.file_path}")
        return

    if not guild.voice_client or not guild.voice_client.is_connected():
        logger.warning(f"[{guild_id}] VC未接続のためスキップ ({audio_task.task_id})")
        return

    try:
        source = discord.FFmpegPCMAudio(
            audio_task.file_path,
            options="-vn -loglevel quiet",
            before_options="-loglevel quiet",
        )
        stop_event = asyncio.Event()

        def after_callback(error):
            if error:
                logger.error(f"[{guild_id}] 再生エラー (callback): {error}")
            if bot.loop.is_running():
                bot.loop.call_soon_threadsafe(stop_event.set)

        guild.voice_client.play(source, after=after_callback)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=PLAYBACK_TIMEOUT)
            logger.info(f"[{guild_id}] 再生完了 ({audio_task.task_id})")
        except asyncio.TimeoutError:
            logger.warning(f"[{guild_id}] 再生タイムアウト ({audio_task.task_id})")
            if guild.voice_client and guild.voice_client.is_playing():
                guild.voice_client.stop()

    except discord.errors.ClientException as e:
        logger.error(f"[{guild_id}] Discord再生エラー: {e}")
    except Exception as e:
        logger.error(f"[{guild_id}] 再生処理エラー: {e}")
