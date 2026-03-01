# src/cogs/voice/dictionary/get_guild_dict.py
import discord
from loguru import logger


async def get_guild_dict(bot, interaction: discord.Interaction) -> dict | None:
    try:
        words_dict = await bot.db.get_dict(interaction.guild.id)
        return words_dict if isinstance(words_dict, dict) else {}
    except Exception as e:
        logger.error(f"[{interaction.guild.id}] 辞書の取得に失敗: {e}")
        embed = discord.Embed(
            title="❌ 辞書の取得エラー",
            description="辞書の取得中にエラーが発生しました。",
            color=discord.Color.red()
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=embed, ephemeral=True)
        return None
