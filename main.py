import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# インテントの設定
intents = discord.Intents.default()
intents.members = True
intents.message_content = True  # チャットを読み上げるために必須

cogs = [
    "src.cogs.voice"
]


class SumireVox(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

    async def setup_hook(self) -> None:
        print("--- Loading Cogs ---")
        for cog in cogs:
            try:
                await self.load_extension(cog)
                print(f"✅ Loaded: {cog}")
            except Exception as e:
                print(f"❌ Failed to load {cog}: {e}")
        print("--------------------")

    async def on_ready(self) -> None:
        print(f"Logged in as {self.user} (ID: {self.user.id})")


bot = SumireVox()


@bot.command()
@commands.is_owner()
async def sync(ctx):
    print("Syncing...")
    # 同期されたコマンドのリストを受け取り、その数を確認する
    synced = await bot.tree.sync()
    await ctx.send(f"Successfully synced {len(synced)} commands.")
    print(f"Synced {len(synced)} commands.")


if __name__ == "__main__":
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN not found in .env file.")
