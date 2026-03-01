# src/cogs/voice/embeds/create_dictionary_add_success_embed.py
import discord


def create_dictionary_add_success_embed(word: str, reading: str) -> discord.Embed:
    return discord.Embed(
        title="✅ 辞書に追加しました",
        description=f"**{word}** → **{reading}**",
        color=discord.Color.green()
    )
