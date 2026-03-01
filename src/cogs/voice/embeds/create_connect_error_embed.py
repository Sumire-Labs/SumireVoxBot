# src/cogs/voice/embeds/create_connect_error_embed.py
import discord


def create_connect_error_embed(error_type: str, detail: str = "") -> discord.Embed:
    titles = {
        "not_in_vc": "❌ 接続エラー",
        "already_connected": "⚠️ 既に接続しています",
        "other_bot": "🚫 チャンネル重複",
        "permission": "❌ 権限エラー",
        "timeout": "❌ 接続タイムアウト",
        "client": "❌ 接続エラー",
    }

    descriptions = {
        "not_in_vc": "ボイスチャンネルに接続してから実行してください。",
        "already_connected": f"既に **{detail}** に接続しています。\n先に `/leave` で切断してください。",
        "other_bot": f"既に **{detail}** がこのチャンネルに参加しています。\n1つのチャンネルに複数のBotを入れることはできません。",
        "permission": f"**{detail}** に接続する権限がありません。\nチャンネルの権限設定を確認してください。",
        "timeout": "ボイスチャンネルへの接続がタイムアウトしました。\nしばらく時間をおいてから再度お試しください。",
        "client": "既にボイスチャンネルに接続しています。",
    }

    colors = {
        "not_in_vc": discord.Color.red(),
        "already_connected": discord.Color.orange(),
        "other_bot": discord.Color.red(),
        "permission": discord.Color.red(),
        "timeout": discord.Color.red(),
        "client": discord.Color.red(),
    }

    return discord.Embed(
        title=titles.get(error_type, "❌ エラー"),
        description=descriptions.get(error_type, "不明なエラーが発生しました。"),
        color=colors.get(error_type, discord.Color.red())
    )
