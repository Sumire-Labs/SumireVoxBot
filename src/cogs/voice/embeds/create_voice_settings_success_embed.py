# src/cogs/voice/embeds/create_voice_setting_success_embed.py
import discord


def create_voice_setting_success_embed(
    speaker_name: str,
    speed: float,
    pitch: float
) -> discord.Embed:
    return discord.Embed(
        title="✅ 声を設定しました",
        description=f"**話者**: {speaker_name}\n**話速**: {speed}\n**音高**: {pitch}",
        color=discord.Color.green()
    )
