# src/cogs/voice/helpers/check_voice_permissions.py
def check_voice_permissions(channel, guild) -> bool:
    permissions = channel.permissions_for(guild.me)
    return permissions.connect and permissions.speak
