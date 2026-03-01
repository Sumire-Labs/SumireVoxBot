# src/cogs/voice/embeds/create_dictionary_delete_success_embed.py
import discord


def create_dictionary_delete_success_embed(word: str) -> discord.Embed:
    return discord.Embed(
        title="✅ 辞書から削除しました",
        description=f"**{word}** を削除しました。",
        color=discord.Color.green()
    )
