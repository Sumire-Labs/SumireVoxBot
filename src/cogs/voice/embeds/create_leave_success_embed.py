# src/cogs/voice/embeds/create_leave_success_embed.py
import discord


def create_leave_success_embed() -> discord.Embed:
    return discord.Embed(
        title="👋 切断しました",
        description="ボイスチャンネルから切断しました。",
        color=discord.Color.blue()
    )
