# src/cogs/voice/session/delete_session_background.py
from loguru import logger


async def delete_session_background(bot, guild_id: int) -> None:
    try:
        await bot.db.delete_voice_session(guild_id)
    except Exception as e:
        logger.error(f"[{guild_id}] セッション削除に失敗: {e}")
