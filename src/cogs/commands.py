import os
import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger


class InviteView(discord.ui.View):
    def __init__(self, bot_info_list: list[dict]):
        super().__init__(timeout=None)
        for info in bot_info_list:
            url = f"https://discord.com/api/oauth2/authorize?client_id={info['id']}&permissions=3145728&scope=bot%20applications.commands"
            self.add_item(discord.ui.Button(label=info['label'], url=url, emoji="🌸"))


class Commands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="invite",
        description="追加のBotを招待します（ブースト済みサーバー限定）"
    )
    async def invite(self, interaction: discord.Interaction):
        """招待リンクを表示する"""
        boost_count = await self.bot.db.get_guild_boost_count(interaction.guild_id)
        bot_instances = await self.bot.db.get_bot_instances()
        
        embed = discord.Embed(
            title="🌸 Bot招待・管理",
            description=f"現在のサーバーのブースト数: **{boost_count}**",
            color=discord.Color.brand_green()
        )

        available_bots = []
        next_goal = None

        # インスタンスのリスト (bot_instances) は id (1, 2, 3...) でソートされている
        # id=1 はメインBotなので、2台目以降は index > 0 (id > 1)
        for i, bi in enumerate(bot_instances):
            if i == 0: continue # メインBotはスキップ
            
            # 修正: 2台目(i=1)は2ブースト、3台目(i=2)は3ブースト...
            # つまり boost_count >= i + 1
            required_boosts = i + 1
            if boost_count >= required_boosts:
                available_bots.append({
                    "id": bi["client_id"],
                    "label": f"{i+1}台目を招待"
                })
            elif next_goal is None:
                next_goal = required_boosts

        if available_bots:
            embed.add_field(
                name="✅ 招待可能なBot",
                value="以下のボタンからサブBotを招待できます。各Botは異なるチャンネルで同時に読み上げが可能です。",
                inline=False
            )
            view = InviteView(available_bots)
            await interaction.response.send_message(embed=embed, view=view)
        else:
            msg = "現在、招待可能なサブBotはありません。"
            if next_goal:
                msg += f"\nあと **{next_goal - boost_count}** ブーストで次のBotが解放されます！"
            elif len(bot_instances) <= 1:
                 msg += "\n現在、追加のサブBotは用意されていません。"
            
            embed.add_field(name="ℹ️ お知らせ", value=msg)
            await interaction.response.send_message(embed=embed, ephemeral=True)

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
