import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import re


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
        guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)

        try:
            while not queue.empty():
                text, author_id = await queue.get()  # タプルで取得

                # DBからユーザー設定を読み込む
                s = await self.bot.db.get_user_setting(author_id)

                file_path = f"{self.temp_dir}/audio_{guild_id}.wav"
                try:
                    await self.bot.vv_client.generate_sound(
                        text=text,
                        speaker_id=s["speaker"],
                        speed=s["speed"],
                        pitch=s["pitch"],
                        output_path=file_path
                    )
                    if guild.voice_client:
                        source = discord.FFmpegPCMAudio(file_path)
                        stop_event = asyncio.Event()
                        guild.voice_client.play(source,
                                                after=lambda e: self.bot.loop.call_soon_threadsafe(stop_event.set))
                        await stop_event.wait()
                finally:
                    queue.task_done()
        finally:
            self.is_processing[guild_id] = False

    @commands.Cog.listener(name="on_message")
    async def read_message(self, message: discord.Message):
        if message.author.bot or not message.guild or not message.guild.voice_client:
            return
        if message.channel.id != self.read_channels.get(message.guild.id):
            return

        content = message.clean_content

        # コードブロックを省略
        content = re.sub(r"```.*?```", "、コードブロック省略、", content, flags=re.DOTALL)

        # URLを省略
        content = re.sub(r'https?://[\w/:%#$&?()~.=+\-]+', '、URL省略、', content)

        # 長文対策
        limit = 50 # 後々設定可能にする
        if len(content) > limit:
            content = content[:limit] + "、以下略"

        # 添付ファイルのチェック
        if message.attachments:
            content += f"、{len(message.attachments)}件の添付ファイル"

        if not content.strip():
            return

        queue = self.get_queue(message.guild.id)
        await queue.put((content, message.author.id))

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

            await interaction.guild.voice_client.disconnect(force=True)
            await interaction.response.send_message("👋 切断しました。")
        else:
            await interaction.response.send_message("❌ Botはボイスチャンネルに接続していません。", ephemeral=True)

    @app_commands.command(name="set_voice", description="自分の声をカスタマイズします")
    @app_commands.choices(speaker=[
        app_commands.Choice(name="ずんだもん", value=3),
        app_commands.Choice(name="四国めたん", value=2),
        app_commands.Choice(name="春日部つむぎ", value=8),
        app_commands.Choice(name="波音リツ", value=9),
    ])
    @app_commands.rename(speaker="キャラクター", speed="スピード", pitch="ピッチ")
    @app_commands.describe(
        speaker="自分の声のキャラクターを変更できます",
        speed="自分の声のスピードを変更できます (デフォルトは1.0)",
        pitch="自分の声のピッチを変更できます (デフォルトは0.0)"
    )
    async def set_voice(self, interaction: discord.Interaction, speaker: int, speed: float = 1.0, pitch: float = 0.0):
        # バリデーション
        speed = max(0.5, min(2.0, speed))
        pitch = max(-0.15, min(0.15, pitch))

        # DBに保存
        await self.bot.db.set_user_setting(interaction.user.id, speaker, speed, pitch)

        await interaction.response.send_message(
            f"✅ {interaction.user.display_name}さんの音声を保存しました！\n"
            f"速度: {speed} / ピッチ: {pitch}", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(Voice(bot))
