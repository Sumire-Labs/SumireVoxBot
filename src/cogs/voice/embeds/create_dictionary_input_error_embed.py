# src/cogs/voice/embeds/create_dictionary_input_error_embed.py
import discord


def create_dictionary_input_error_embed(error_type: str, word: str = None) -> discord.Embed:
    if error_type == "missing_params":
        return discord.Embed(
            title="❌ 入力エラー",
            description="単語と読み方を両方指定してください。",
            color=discord.Color.red()
        )
    elif error_type == "invalid_reading":
        return discord.Embed(
            title="❌ 入力エラー",
            description="読み方はカタカナで入力してください。",
            color=discord.Color.red()
        )
    elif error_type == "missing_word":
        return discord.Embed(
            title="❌ 入力エラー",
            description="削除する単語を指定してください。",
            color=discord.Color.red()
        )
    elif error_type == "not_found":
        return discord.Embed(
            title="❌ 見つかりません",
            description=f"**{word}** は辞書に登録されていません。",
            color=discord.Color.red()
        )
    else:
        return discord.Embed(
            title="❌ エラー",
            description="辞書の操作中にエラーが発生しました。",
            color=discord.Color.red()
        )
