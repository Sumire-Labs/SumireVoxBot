# src/cogs/voice/commands/dictionary_list.py
import discord
from discord.ext import commands

from src.utils.views import DictionaryView, create_dictionary_embed


async def dictionary_list(
    bot: commands.Bot,
    interaction: discord.Interaction,
    words_dict: dict
) -> None:
    try:
        if not words_dict:
            embed = discord.Embed(
                title="📖 辞書一覧",
                description="登録されている単語はありません。",
                color=discord.Color.blue()
            )
            return await interaction.response.send_message(embed=embed)

        embed = create_dictionary_embed(words_dict, page=0)
        view = DictionaryView(bot.db, bot, words_dict) if len(words_dict) > 10 else None
        return await interaction.response.send_message(embed=embed, view=view)

    except discord.errors.HTTPException as e:
        from loguru import logger
        logger.error(f"[{interaction.guild.id}] 辞書一覧送信中にHTTPエラー: {e}")
        embed = discord.Embed(
            title="❌ エラー",
            description="辞書一覧の送信中に通信エラーが発生しました。",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        from loguru import logger
        logger.error(f"[{interaction.guild.id}] 辞書一覧表示中にエラー: {e}")
        embed = discord.Embed(
            title="❌ エラー",
            description="辞書一覧の表示中にエラーが発生しました。",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
