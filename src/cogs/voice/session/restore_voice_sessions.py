# src/cogs/voice/session/restore_voice_sessions.py
import asyncio
from loguru import logger

from .try_restore_session import try_restore_session
from .delete_session_background import delete_session_background


async def restore_voice_sessions(bot, read_channels: dict) -> None:
    logger.info("Restoring voice sessions from database...")

    try:
        sessions = await bot.db.get_voice_sessions_by_bot(bot.user.id)
    except Exception as e:
        logger.error(f"セッション取得に失敗: {e}")
        return

    if not sessions:
        logger.info("復元するセッションはありません")
        return

    logger.info(f"{len(sessions)}件のセッションを復元中...")

    restored = 0
    failed = 0

    for session in sessions:
        guild_id = session["guild_id"]
        result = await try_restore_session(
            bot,
            read_channels,
            guild_id,
            session["voice_channel_id"],
            session["text_channel_id"]
        )

        if result:
            restored += 1
        else:
            failed += 1
            asyncio.create_task(delete_session_background(bot, guild_id))

    logger.success(f"セッション復元完了: {restored}件成功, {failed}件失敗")
