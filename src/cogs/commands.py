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
        name="sync"
    )
    @commands.is_owner()
    async def sync(self, interaction: discord.Interaction):
        logger.info(f"コマンド同期リクエストを受信しました...")
        try:
            await interaction.response.defer(ephemeral=True)
            synced = await self.bot.tree.sync()
            logger.success(f"{len(synced)}個のコマンドを同期しました")
            await interaction.followup.send(f"{len(synced)}個のコマンドを同期しました")
        except Exception as e:
            logger.error(f"コマンド同期中にエラーが発生しました: {e}")
            await interaction.followup.send(f"コマンド同期中にエラーが発生しました: {str(e)}")


async def setup(bot):
    await bot.add_cog(Commands(bot))
