# src/cogs/voice/helpers/check_other_bot_in_channel.py
import discord


def check_other_bot_in_channel(channel, bot_id: int):
    return discord.utils.find(
        lambda m: m.bot and m.id != bot_id and ("Sumire" in m.name or "Vox" in m.name),
        channel.members
    )
