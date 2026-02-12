import os
import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="ping",
        description="Botの応答速度を確認します"
    )
    async def ping(self, interaction: discord.Interaction):
        latency = round(self.bot.latency * 1000)
        await interaction.response.send_message(f"🏓 Pong! レイテンシ: {latency}ms")

    @app_commands.command(
        name="sync",
        description="Cogのリロードとコマンドの同期を行います (開発者限定)"
    )
    @commands.is_owner()
    async def sync(self, interaction: discord.Interaction):
        logger.info("Cogのリロードとコマンド同期のリクエストを受信しました...")
        try:
            await interaction.response.defer(ephemeral=True)

            # 1. Cogのリロード
            reloaded_cogs = []
            failed_cogs = []
            cogs_dir = "src/cogs"

            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py"):
                    cog_name = f"src.cogs.{filename[:-3]}"
                    try:
                        await self.bot.reload_extension(cog_name)
                        reloaded_cogs.append(filename)
                    except Exception as e:
                        logger.error(f"Failed to reload {cog_name}: {e}")
                        failed_cogs.append(f"{filename} ({str(e)})")

            # 2. コマンドの同期
            synced = await self.bot.tree.sync()

            # Embedの構築
            embed = discord.Embed(
                title="🔄 同期完了",
                color=discord.Color.green() if not failed_cogs else discord.Color.orange()
            )

            embed.add_field(
                name="✅ コマンド同期",
                value=f"{len(synced)}個のコマンドを同期しました。",
                inline=False
            )

            embed.add_field(
                name="📦 リロード完了",
                value=', '.join(reloaded_cogs) if reloaded_cogs else "なし",
                inline=False
            )

            if failed_cogs:
                embed.add_field(
                    name="❌ リロード失敗",
                    value='\n'.join(failed_cogs),
                    inline=False
                )

            logger.success(f"同期完了: {len(synced)}個のコマンド, {len(reloaded_cogs)}個のCog")
            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"同期中にエラーが発生しました: {e}")
            error_embed = discord.Embed(
                title="❌ エラー",
                description=f"同期中にエラーが発生しました: {str(e)}",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)


async def setup(bot):
    await bot.add_cog(Commands(bot))
