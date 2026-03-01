# src/cogs/voice/handlers/on_guild_remove.py
import discord
from loguru import logger


async def on_guild_remove(bot, guild: discord.Guild) -> None:
    try:
        await bot.db.delete_guild_boosts_by_guild(guild.id)
        logger.info(f"[{guild.id}] サーバー脱退に伴いブースト情報を削除")
    except Exception as e:
        logger.error(f"[{guild.id}] ブースト削除失敗: {e}")
