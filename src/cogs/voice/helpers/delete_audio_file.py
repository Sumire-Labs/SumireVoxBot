# src/cogs/voice/helpers/delete_audio_file.py
import os
from loguru import logger

from ..models.audio_task import AudioTask


def delete_audio_file(audio_task: AudioTask, guild_id: int) -> None:
    file_path = audio_task.file_path
    if not file_path or not os.path.exists(file_path):
        return

    try:
        os.remove(file_path)
        logger.debug(f"[{guild_id}] 一時ファイルを削除: {file_path}")
    except PermissionError as e:
        logger.warning(f"[{guild_id}] ファイル削除権限エラー: {e}")
    except OSError as e:
        logger.warning(f"[{guild_id}] ファイル削除OSエラー: {e}")
    except Exception as e:
        logger.error(f"[{guild_id}] ファイル削除エラー: {e}")
