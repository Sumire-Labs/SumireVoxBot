# src/cogs/voice/commands/dictionary_delete.py
import discord
from loguru import logger


async def dictionary_delete(
    bot,
    interaction: discord.Interaction,
    words_dict: dict,
    word: str
) -> None:
    if not word:
        embed = discord.Embed(
            title="❌ 入力エラー",
            description="削除する単語を指定してください。",
            color=discord.Color.red()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    if word not in words_dict:
        embed = discord.Embed(
            title="❌ 見つかりません",
            description=f"**{word}** は辞書に登録されていません。",
            color=discord.Color.red()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    del words_dict[word]

    try:
        await bot.db.add_or_update_dict(interaction.guild.id, words_dict)
        embed = discord.Embed(
            title="✅ 辞書から削除しました",
            description=f"**{word}** を削除しました。",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed)

    except Exception as e:
        logger.error(f"[{interaction.guild.id}] 辞書の削除に失敗: {e}")
        embed = discord.Embed(
            title="❌ エラー",
            description="辞書の削除中にエラーが発生しました。",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
