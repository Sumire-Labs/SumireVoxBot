# src/cogs/voice/commands/set_voice.py
import discord
from loguru import logger


async def set_voice(
    bot,
    interaction: discord.Interaction,
    speaker_value: int,
    speaker_name: str,
    speed: float,
    pitch: float
) -> None:
    # 値の範囲チェック
    if not (0.5 <= speed <= 2.0):
        embed = discord.Embed(
            title="❌ 無効な値",
            description="話速は 0.5〜2.0 の範囲で指定してください。",
            color=discord.Color.red()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    if not (-0.15 <= pitch <= 0.15):
        embed = discord.Embed(
            title="❌ 無効な値",
            description="音高は -0.15〜0.15 の範囲で指定してください。",
            color=discord.Color.red()
        )
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    try:
        await bot.db.set_user_setting(
            interaction.user.id,
            speaker_value,
            speed,
            pitch
        )

        embed = discord.Embed(
            title="✅ 声を設定しました",
            description=f"**話者**: {speaker_name}\n**話速**: {speed}\n**音高**: {pitch}",
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"[{interaction.guild.id}] 声の設定に失敗: {e}")
        embed = discord.Embed(
            title="❌ エラー",
            description="声の設定中にエラーが発生しました。",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
