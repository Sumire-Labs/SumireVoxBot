# src/cogs/voice/embeds/create_voice_setting_error_embed.py
import discord


def create_voice_setting_error_embed(error_type: str) -> discord.Embed:
    if error_type == "invalid_speed":
        return discord.Embed(
            title="❌ 無効な値",
            description="話速は 0.5〜2.0 の範囲で指定してください。",
            color=discord.Color.red()
        )
    elif error_type == "invalid_pitch":
        return discord.Embed(
            title="❌ 無効な値",
            description="音高は -0.15〜0.15 の範囲で指定してください。",
            color=discord.Color.red()
        )
    else:
        return discord.Embed(
            title="❌ エラー",
            description="声の設定中にエラーが発生しました。",
            color=discord.Color.red()
        )
