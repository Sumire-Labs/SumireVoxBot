# src/cogs/voice/embeds/create_auto_join_embed.py
import discord


def create_auto_join_embed(channel_name: str) -> discord.Embed:
    return discord.Embed(
        title="✅ 自動接続しました",
        description=f"**{channel_name}** への入室を検知したため、自動接続しました。",
        color=discord.Color.green()
    )
