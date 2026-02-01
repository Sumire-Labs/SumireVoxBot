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
        description="Pongを返します"
    )
    async def ping(self, interaction: discord.Interaction):
        return await interaction.response.send_message(f"Pong! {self.bot.latency * 1000:.2f}ms", ephemeral=True)

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

            # メッセージの構築
            res_msg = f"✅ {len(synced)}個のコマンドを同期しました。\n"
            res_msg += f"📦 リロード完了: {', '.join(reloaded_cogs)}"

            if failed_cogs:
                res_msg += f"\n❌ リロード失敗: {', '.join(failed_cogs)}"

            logger.success(f"同期完了: {len(synced)}個のコマンド, {len(reloaded_cogs)}個のCog")
            await interaction.followup.send(res_msg)

        except Exception as e:
            logger.error(f"同期中にエラーが発生しました: {e}")
            await interaction.followup.send(f"同期中にエラーが発生しました: {str(e)}")


async def setup(bot):
    await bot.add_cog(Commands(bot))
