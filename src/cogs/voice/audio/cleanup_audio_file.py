# src/cogs/voice/audio/cleanup_audio_file.py
import os
import asyncio
from loguru import logger


async def cleanup_audio_file(file_path: str, guild_id: int) -> None:
    try:
        if os.path.exists(file_path):
            await asyncio.sleep(0.5)
            os.remove(file_path)
            logger.debug(f"[{guild_id}] 一時ファイルを削除: {file_path}")
    except Exception as e:
        logger.warning(f"[{guild_id}] 一時ファイルの削除に失敗: {e}")
