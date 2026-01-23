import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio


# noinspection PyUnresolvedReferences
class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_dir = "temp"
        self.queues = {}
        self.is_processing = {}
        self.read_channels = {}

        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def get_queue(self, guild_id: int) -> asyncio.Queue:
        if guild_id not in self.queues:
            self.queues[guild_id] = asyncio.Queue()
            self.is_processing[guild_id] = False
        return self.queues[guild_id]

    async def play_next(self, guild_id: int):
        self.is_processing[guild_id] = True
        queue = self.get_queue(guild_id)

        # guildオブジェクトを確実に取得
        guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)

        try:
            while not queue.empty():
                text = await queue.get()
                file_path = f"{self.temp_dir}/audio_{guild_id}.wav"

                try:
                    await self.bot.vv_client.generate_sound(
                        text=text,
                        speaker_id=1,
                        output_path=file_path
                    )

                    if guild.voice_client and guild.voice_client.is_connected():
                        source = discord.FFmpegPCMAudio(file_path)
                        stop_event = asyncio.Event()

                        def after_playing(error):
                            if error:
                                print(f"Playback error: {error}")
                            self.bot.loop.call_soon_threadsafe(stop_event.set)

                        guild.voice_client.play(source, after=after_playing)
                        await stop_event.wait()

                except Exception as e:
                    print(f"[{guild_id}] Playback Error: {e}")
                finally:
                    queue.task_done()
        finally:
            self.is_processing[guild_id] = False

    @commands.Cog.listener(name="on_message")
    async def read_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.guild.voice_client:
            return

        # 追加: コマンドを打ったチャンネル以外は無視する設定
        if message.channel.id != self.read_channels.get(message.guild.id):
            return

        queue = self.get_queue(message.guild.id)
        await queue.put(message.clean_content)

        if not self.is_processing[message.guild.id]:
            asyncio.create_task(self.play_next(message.guild.id))

    @commands.Cog.listener(name="on_voice_state_update")
    async def clear_info_on_leave(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Bot自身がVCから切断されたら情報をクリアする"""
        if member.id == self.bot.user.id and before.channel is not None and after.channel is None:
            guild_id = member.guild.id
            # データの掃除
            self.read_channels.pop(guild_id, None)
            # キューを空にする
            if guild_id in self.queues:
                while not self.queues[guild_id].empty():
                    try:
                        self.queues[guild_id].get_nowait()
                    except asyncio.QueueEmpty:
                        break
            print(f"[{guild_id}] VC切断を確認したため、データをクリアしました。")

    @app_commands.command(name="join", description="ボイスチャンネルに接続し、このチャンネルを読み上げます")
    async def join(self, interaction: discord.Interaction):
        if interaction.user.voice:
            # 読み上げチャンネルを記憶
            self.read_channels[interaction.guild.id] = interaction.channel.id

            channel = interaction.user.voice.channel
            await channel.connect()
            await interaction.response.send_message(
                f"✅ {channel.name} に接続しました。このチャンネルのチャットを読み上げます。")
        else:
            await interaction.response.send_message("❌ ボイスチャンネルに接続してから実行してください。", ephemeral=True)

    @app_commands.command(name="leave", description="切断して読み上げを終了します")
    async def leave(self, interaction: discord.Interaction):
        if interaction.guild.voice_client:
            # チャンネルの記憶を削除
            self.read_channels.pop(interaction.guild.id, None)

            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 切断しました。")
        else:
            await interaction.response.send_message("❌ Botはボイスチャンネルに接続していません。", ephemeral=True)


async def setup(bot):
    await bot.add_cog(Voice(bot))
