# src/cogs/voice/commands/dictionary_add.py
import discord
from loguru import logger

from ..validators.is_katakana import is_katakana


async def dictionary_add(
    bot,
    interaction: discord.Interaction,
    words_dict: dict,
    word: str,
    reading: str
) -> None:
    if not word or not reading:
        embed = discord.Embed(
            title="❌ 入力エラー",
            description="単語と読み方を両方指定してください。",
            color=discord.Color.red()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    if not is_katakana(reading):
        embed = discord.Embed(
            title="❌ 入力エラー",
            description="読み方はカタカナで入力してください。",
            color=discord.Color.red()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    words_dict[word] = reading

    try:
        await bot.db.add_or_update_dict(interaction.guild.id, words_dict)
        embed = discord.Embed(
            title="✅ 辞書に追加しました",
            description=f"**{word}** → **{reading}**",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"[{interaction.guild.id}] 辞書の追加に失敗: {e}")
        embed = discord.Embed(
            title="❌ エラー",
            description="辞書の追加中にエラーが発生しました。",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
