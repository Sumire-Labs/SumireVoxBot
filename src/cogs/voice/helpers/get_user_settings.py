# src/cogs/voice/helpers/get_user_settings.py
from loguru import logger


async def get_user_settings(bot, author_id: int, guild_id: int) -> dict:
    try:
        settings = await bot.db.get_user_setting(author_id)
    except Exception as e:
        logger.error(f"[{guild_id}] ユーザー設定の取得に失敗 (user_id: {author_id}): {e}")
        settings = {"speaker": 1, "speed": 1.0, "pitch": 0.0}

    try:
        is_boosted = await bot.db.is_guild_boosted(guild_id)
    except Exception:
        is_boosted = False

    if not is_boosted:
        settings["speed"] = 1.0
        settings["pitch"] = 0.0

    return settings
