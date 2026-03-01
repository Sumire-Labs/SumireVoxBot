# src/cogs/voice/embeds/create_connect_success_embed.py
import discord


def create_connect_success_embed(channel_name: str) -> discord.Embed:
    return discord.Embed(
        title="✅ 接続しました",
        description=f"**{channel_name}** に接続しました。\nこのチャンネルのチャットを読み上げます。",
        color=discord.Color.green()
    )
