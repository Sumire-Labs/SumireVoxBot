# src/cogs/voice/embeds/create_leave_error_embed.py
import discord


def create_leave_error_embed(error_type: str) -> discord.Embed:
    if error_type == "not_connected":
        return discord.Embed(
            title="❌ 接続エラー",
            description="Botはボイスチャンネルに接続していません。",
            color=discord.Color.red()
        )
    elif error_type == "http_error":
        return discord.Embed(
            title="❌ 切断エラー",
            description="切断中に通信エラーが発生しました。\nBotは既に切断されている可能性があります。",
            color=discord.Color.red()
        )
    else:
        return discord.Embed(
            title="❌ エラー",
            description="コマンド実行中にエラーが発生しました。",
            color=discord.Color.red()
        )
