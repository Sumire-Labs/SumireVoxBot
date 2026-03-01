# src/cogs/voice/dictionary/load_guild_dict.py
from loguru import logger


async def load_guild_dict(bot, guild_id: int) -> None:
    try:
        await bot.db.load_guild_dict(guild_id)
        logger.debug(f"[{guild_id}] 辞書をロード")
    except Exception as e:
        logger.error(f"[{guild_id}] 辞書のロードに失敗: {e}")
