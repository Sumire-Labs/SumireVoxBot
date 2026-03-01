# src/cogs/voice/helpers/get_human_members.py
def get_human_members(channel) -> list:
    return [m for m in channel.members if not m.bot]
