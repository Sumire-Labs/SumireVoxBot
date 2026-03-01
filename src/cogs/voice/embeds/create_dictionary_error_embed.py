# src/cogs/voice/embeds/create_dictionary_error_embed.py
import discord


def create_dictionary_error_embed() -> discord.Embed:
    return discord.Embed(
        title="❌ 辞書の取得エラー",
        description="辞書の取得中にエラーが発生しました。",
        color=discord.Color.red()
    )
