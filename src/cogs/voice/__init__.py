# src/cogs/voice/__init__.py
from .voice_cog import Voice


async def setup(bot):
    await bot.add_cog(Voice(bot))
