# src/cogs/voice/embeds/create_permission_error_embed.py
import discord


def create_permission_error_embed(action: str) -> discord.Embed:
    return discord.Embed(
        title="❌ 権限エラー",
        description=f"{action}する権限がありません。",
        color=discord.Color.red()
    )
