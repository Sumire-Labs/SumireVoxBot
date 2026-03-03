import discord


def create_config_error_embed(error_type: str):
    titles = {
        "permission": "❌ 権限エラー",
        "display": "❌ 設定画面表示エラー"
    }

    descriptions = {
        "permission": "このコマンドを実行するには、「サーバー管理」権限が必要です。",
        "display": "設定画面を表示中にエラーが発生しました。"
    }

    return discord.Embed(
        title=titles.get(error_type, "❌ エラー"),
        description=descriptions.get(error_type, "エラーが発生しました。"),
        color=discord.Color.red()
    )