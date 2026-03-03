# src/cogs/voice/commands/config.py
import discord
from loguru import logger

from src.utils.views import ConfigSearchView
from ..embeds.create_config_embed import create_config_embed
from ..embeds.create_config_error_embed import create_config_error_embed


async def config(bot, interaction: discord.Interaction):
    is_admin = interaction.user.guild_permissions.manage_guild
    is_owner = await bot.is_owner(interaction.user)

    if not (is_admin or is_owner):
        embed = create_config_error_embed("permission")
        return await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    try:
        settings = await bot.db.get_guild_settings(interaction.guild.id)
        is_boosted = await bot.db.is_guild_boosted(interaction.guild.id)
        embed = create_config_embed(bot, interaction.guild, settings, is_boosted)
        view = ConfigSearchView(bot.db, bot)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
        view.message = await interaction.original_response()
    except Exception as e:
        logger.error(f"[{interaction.guild.id}] 設定画面の表示に失敗しました: {e}")
        embed = create_config_error_embed("display")
        await interaction.response.send_message(embed=embed, ephemeral=True)