# src/cogs/voice/commands/leave.py
import asyncio
import discord
from loguru import logger


async def leave(
    bot,
    interaction: discord.Interaction,
    read_channels: dict,
    delete_session_func
) -> None:
    try:
        if not interaction.guild.voice_client:
            embed = discord.Embed(
                title="❌ 接続エラー",
                description="Botはボイスチャンネルに接続していません。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        guild_id = interaction.guild.id

        # 変数から削除（優先）
        read_channels.pop(guild_id, None)

        # 切断（優先）
        try:
            await interaction.guild.voice_client.disconnect(force=True)

            embed = discord.Embed(
                title="👋 切断しました",
                description="ボイスチャンネルから切断しました。",
                color=discord.Color.blue()
            )
            await interaction.response.send_message(embed=embed)

            logger.info(f"[{guild_id}] VCから切断しました。")

            # 辞書をアンロード（バックグラウンド）
            asyncio.create_task(bot.db.unload_guild_dict(guild_id))

            # DBからセッションを削除（バックグラウンド）
            asyncio.create_task(delete_session_func(guild_id))

        except discord.errors.HTTPException as e:
            logger.error(f"[{guild_id}] VC切断中にHTTPエラー: {e}")
            embed = discord.Embed(
                title="❌ 切断エラー",
                description="切断中に通信エラーが発生しました。\nBotは既に切断されている可能性があります。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    except Exception as e:
        logger.error(f"[{interaction.guild.id}] leaveコマンド実行中にエラー: {e}")
        embed = discord.Embed(
            title="❌ エラー",
            description="コマンド実行中にエラーが発生しました。",
            color=discord.Color.red()
        )
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
