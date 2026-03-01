# src/cogs/voice/audio/generate_audio.py
import os
import asyncio
from loguru import logger

from ..models.audio_task import AudioTask
from ..helpers.get_user_settings import get_user_settings
from .normalize_text import normalize_text


async def generate_audio(bot, audio_task: AudioTask, guild_id: int) -> None:
    try:
        settings = await get_user_settings(bot, audio_task.author_id, guild_id)
        normalized = normalize_text(audio_task.text)

        logger.debug(f"[{guild_id}] 音声生成開始 ({audio_task.task_id})")

        await bot.vv_client.generate_sound(
            text=normalized,
            speaker_id=settings["speaker"],
            speed=settings["speed"],
            pitch=settings["pitch"],
            output_path=audio_task.file_path
        )

        if not os.path.exists(audio_task.file_path):
            logger.error(f"[{guild_id}] 音声ファイルが生成されませんでした")
            audio_task.is_failed = True

        audio_task.is_ready.set()
        logger.debug(f"[{guild_id}] 音声生成完了 ({audio_task.task_id})")

    except asyncio.CancelledError:
        logger.warning(f"[{guild_id}] 音声生成がキャンセル ({audio_task.task_id})")
        audio_task.is_failed = True
        audio_task.is_ready.set()
        if os.path.exists(audio_task.file_path):
            try:
                os.remove(audio_task.file_path)
            except Exception:
                pass
        raise

    except Exception as e:
        logger.error(f"[{guild_id}] 音声生成エラー ({audio_task.task_id}): {e}")
        audio_task.is_failed = True
        audio_task.is_ready.set()
