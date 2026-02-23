import discord
from discord import app_commands
from discord.ext import commands
from loguru import logger


class Boost(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    boost_group = app_commands.Group(name="boost", description="サーバーブースト関連のコマンド")

    @boost_group.command(
        name="activate",
        description="このサーバーに対して自分のブースト枠を使用します"
    )
    async def activate(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        guild_id = interaction.guild_id
        user_id = interaction.user.id

        logger.debug(f"/boost activate called by {user_id} for guild {guild_id}")

        try:
            # 現在のブースト数を取得
            boost_count = await self.db.get_guild_boost_count(guild_id)
            bot_instances = await self.db.get_bot_instances()
            max_boosts = len(bot_instances)

            logger.debug(f"boost_count: {boost_count}, max_boosts: {max_boosts}")

            if boost_count >= max_boosts:
                await interaction.followup.send(f"このサーバーはすでに最大数({max_boosts})までブーストされています。", ephemeral=True)
                return

            # スロットに空きがあるか確認
            status = await self.db.get_user_slots_status(user_id)
            logger.debug(f"user_slots_status: {status}")

            if status["total"] == 0:
                await interaction.followup.send(
                    "✨ **プレミアムプランのご案内**\n"
                    "現在ブースト枠を所有していません。Webダッシュボードからプレミアムプランを購入することで、このサーバーをブーストし、読み上げ制限（50文字→500文字）を解除できます！\n"
                    "また、2つ以上のブーストを適用することで、サブBotを追加して同時に複数のチャンネルで読み上げることも可能です。",
                    ephemeral=True
                )
                return
            
            if status["total"] <= status["used"]:
                await interaction.followup.send(
                    f"空きスロットがありません。 (使用中: {status['used']}/{status['total']})\n"
                    "既存のブーストを解除するか、追加のスロットを購入してください。", 
                    ephemeral=True
                )
                return

            # ブーストを適用
            success = await self.db.activate_guild_boost(guild_id, user_id)
            logger.debug(f"activate_guild_boost success: {success}")

            if success:
                embed = discord.Embed(
                    title="✨ サーバーブースト完了",
                    description=f"{interaction.user.mention} がこのサーバーをブーストしました！",
                    color=discord.Color.gold()
                )
                if boost_count == 0:
                    embed.description += "\n1つ目のブーストにより、読み上げ制限が緩和されました。"
                else:
                    embed.description += f"\n{boost_count + 1}つ目のブーストにより、新たなサブBotの招待が可能になりました。"
                
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("ブーストの適用に失敗しました。すでに他のユーザーによって最大数までブーストされた可能性があります。", ephemeral=True)
        except Exception as e:
            logger.error(f"Error in /boost activate: {e}")
            await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)

    @boost_group.command(
        name="status",
        description="このサーバーのブースト状況を表示します"
    )
    async def status(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_id = interaction.guild_id
        
        try:
            boost_count = await self.db.get_guild_boost_count(guild_id)
            
            # デバッグログ
            logger.debug(f"/boost status called for guild_id={guild_id} ({type(guild_id)}). DB count={boost_count}")
            
            embed = discord.Embed(
                title="💎 サーバーブースト状況",
                color=discord.Color.blue()
            )

            if boost_count > 0:
                embed.description = f"このサーバーはブーストされています。\n現在の合計ブースト数: **{boost_count}**"
                
                # ブースター一覧の表示（複数対応）
                booster_names = []
                async with self.db.pool.acquire() as conn:
                    boosters = await conn.fetch("SELECT user_id FROM guild_boosts WHERE guild_id = $1::BIGINT", int(guild_id))
                    for b in boosters:
                        uid = b["user_id"]
                        member = interaction.guild.get_member(int(uid))
                        if not member:
                            try:
                                member = await self.bot.fetch_user(int(uid))
                            except:
                                member = f"ID: {uid}"
                        
                        name = member.mention if isinstance(member, (discord.Member, discord.User)) else member
                        booster_names.append(name)
                
                embed.add_field(name="ブースター", value="\n".join(booster_names) or "不明")
                embed.set_thumbnail(url="https://cdn.discordapp.com/emojis/715774843200110603.gif?v=1")
            else:
                embed.description = "このサーバーはブーストされていません。"
                embed.add_field(name="ブースト方法", value="`/boost activate` コマンドを使用して、自分のブースト枠を適用できます。")

            # ユーザー自身の状況も表示
            user_status = await self.db.get_user_slots_status(interaction.user.id)
            if user_status["total"] > 0:
                embed.add_field(
                    name="あなたのブースト枠", 
                    value=f"{user_status['used']} / {user_status['total']} 使用中",
                    inline=False
                )

            await interaction.followup.send(embed=embed)
        except Exception as e:
            logger.error(f"Error in /boost status: {e}")
            await interaction.followup.send(f"エラーが発生しました: {e}", ephemeral=True)

    @boost_group.command(
        name="deactivate",
        description="このサーバーから自分のブースト枠を解除します"
    )
    async def deactivate(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_id = interaction.guild_id
        user_id = interaction.user.id

        try:
            # 自分がこのサーバーをブーストしているか、何個ブーストしているか確認
            async with self.db.pool.acquire() as conn:
                user_boost_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM guild_boosts WHERE guild_id = $1::BIGINT AND user_id = $2",
                    int(guild_id),
                    str(user_id)
                )
            
            if user_boost_count == 0:
                await interaction.followup.send("このサーバーにあなたのブーストは見つかりませんでした。", ephemeral=True)
                return

            # ブーストを解除（1つ分）
            success = await self.db.deactivate_guild_boost(guild_id, user_id)
            
            if success:
                embed = discord.Embed(
                    title="✅ サーバーブースト解除",
                    description="このサーバーのブーストを1つ解除しました。枠があなたに返却され、他のサーバーで使用できるようになります。",
                    color=discord.Color.green()
                )
                if user_boost_count > 1:
                    embed.description += f"\n(残り {user_boost_count - 1} 個のブーストが継続中です)"
                
                await interaction.followup.send(embed=embed)
            else:
                # DB関数で False が返った場合（通常は row なしだが、直前のカウントで見つかっているはずなので競合の可能性）
                await interaction.followup.send("ブーストの解除に失敗しました。他の端末で既に解除された可能性があります。", ephemeral=True)
        
        except Exception as e:
            logger.error(f"Error in /boost deactivate (guild: {guild_id}, user: {user_id}): {e}")
            await interaction.followup.send("システムエラーが発生しました。時間をおいて再度お試しください。", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Boost(bot))
