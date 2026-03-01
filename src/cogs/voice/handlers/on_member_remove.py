# src/cogs/voice/handlers/on_member_remove.py
import discord
from loguru import logger


async def on_member_remove(bot, member: discord.Member) -> None:
    try:
        booster_id = await bot.db.get_guild_booster(member.guild.id)
        if booster_id == str(member.id):
            await bot.db.deactivate_guild_boost(member.guild.id, member.id)
            logger.info(f"[{member.guild.id}] ブースター({member.id})脱退によりブースト解除")
    except Exception as e:
        logger.error(f"[{member.guild.id}] ブーストチェック失敗: {e}")
