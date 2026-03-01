# src/cogs/voice/commands/join.py
import asyncio
import discord
from loguru import logger

from ..helpers.check_other_bot_in_channel import check_other_bot_in_channel
from ..embeds.create_connect_success_embed import create_connect_success_embed
from ..embeds.create_connect_error_embed import create_connect_error_embed
from ..session.save_voice_session import save_voice_session
from ..dictionary.load_guild_dict import load_guild_dict


async def join(
    bot,
    interaction: discord.Interaction,
    read_channels: dict
) -> None:
    if not interaction.user.voice:
        embed = create_connect_error_embed("not_in_vc")
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    channel = interaction.user.voice.channel
    guild_id = interaction.guild.id

    if interaction.guild.voice_client:
        embed = create_connect_error_embed("already_connected", interaction.guild.voice_client.channel.name)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    other_bot = check_other_bot_in_channel(channel, bot.user.id)
    if other_bot:
        embed = create_connect_error_embed("other_bot", other_bot.display_name)
        return await interaction.response.send_message(embed=embed, ephemeral=True)

    try:
        await channel.connect()
        read_channels[guild_id] = interaction.channel.id

        embed = create_connect_success_embed(channel.name)
        await interaction.response.send_message(embed=embed)

        logger.success(f"[{guild_id}] {channel.name} に接続")

        asyncio.create_task(load_guild_dict(bot, guild_id))
        asyncio.create_task(save_voice_session(bot, guild_id, channel.id, interaction.channel.id))

    except discord.errors.ClientException:
        embed = create_connect_error_embed("client")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except discord.errors.Forbidden:
        embed = create_connect_error_embed("permission", channel.name)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    except asyncio.TimeoutError:
        embed = create_connect_error_embed("timeout")
        await interaction.response.send_message(embed=embed, ephemeral=True)
