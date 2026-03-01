# src/cogs/voice/embeds/create_reconnect_embed.py
import discord


def create_reconnect_embed(channel_name: str) -> discord.Embed:
    return discord.Embed(
        title="🔄 再接続しました",
        description=f"Botの再起動により **{channel_name}** に再接続しました。\n読み上げを再開します。",
        color=discord.Color.blue()
    )
