# src/cogs/voice/session/save_voice_session.py
from loguru import logger


async def save_voice_session(
    bot,
    guild_id: int,
    voice_channel_id: int,
    text_channel_id: int
) -> None:
    try:
        await bot.db.save_voice_session(
            guild_id=guild_id,
            voice_channel_id=voice_channel_id,
            text_channel_id=text_channel_id,
            bot_id=bot.user.id
        )
        logger.debug(f"[{guild_id}] セッションを保存")
    except Exception as e:
        logger.error(f"[{guild_id}] セッション保存に失敗: {e}")
