# src/cogs/voice/embeds/create_dictionary_list_empty_embed.py
import discord


def create_dictionary_list_empty_embed() -> discord.Embed:
    return discord.Embed(
        title="📖 辞書一覧",
        description="登録されている単語はありません。",
        color=discord.Color.blue()
    )
