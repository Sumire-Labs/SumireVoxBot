# src/cogs/voice/dictionary/apply_dictionary.py
import re
from loguru import logger


async def apply_dictionary(bot, content: str, guild_id: int) -> str:
    if not guild_id or guild_id == 0:
        return content

    try:
        words = await bot.db.get_dict(guild_id)
    except Exception as e:
        logger.error(f"[{guild_id}] 辞書の取得に失敗: {e}")
        return content

    if not words or not isinstance(words, dict):
        return content

    for word in sorted(words.keys(), key=len, reverse=True):
        pattern = re.compile(re.escape(str(word)), re.IGNORECASE)
        content = pattern.sub(str(words[word]), content)

    return content
