# src/cogs/voice/voice_cog.py

import os
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
from loguru import logger

# Handlers
from .handlers.on_ready import on_ready
from .handlers.on_message import on_message
from .handlers.on_voice_state_update_notification import on_voice_state_update_notification
from .handlers.on_voice_state_update_auto_join import on_voice_state_update_auto_join
from .handlers.on_voice_state_update_auto_leave import on_voice_state_update_auto_leave
from .handlers.on_voice_state_update_clear_on_leave import on_voice_state_update_clear_on_leave
from .handlers.on_guild_remove import on_guild_remove
from .handlers.on_member_remove import on_member_remove

# Commands
from .commands.join import join
from .commands.leave import leave
from .commands.set_voice import set_voice
from .commands.dictionary_list import dictionary_list
from .commands.dictionary_add import dictionary_add
from .commands.dictionary_delete import dictionary_delete
from .commands.config import config

# Dictionary helper
from .dictionary.get_guild_dict import get_guild_dict

# Session
from .session.delete_session_background import delete_session_background

# Embed
from .embeds.create_config_embed import create_config_embed


class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_dir = "temp"
        self.queues = {}
        self.is_processing = {}
        self.read_channels = {}
        self._state = {}

        load_dotenv()
        self.GLOBAL_DICT_ID = int(os.getenv("GLOBAL_DICT_ID", "0"))

        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
            logger.info(f"一時ディレクトリを作成: {self.temp_dir}")

    # ========== Helper Methods ==========

    async def _delete_session_background(self, guild_id: int):
        await delete_session_background(self.bot, guild_id)

    def create_config_embed(self, guild: discord.Guild, settings, is_boosted=False) -> discord.Embed:
        """設定表示用のEmbed（views.pyから参照される）"""
        return create_config_embed(self.bot, guild, settings, is_boosted)

    # ========== Event Listeners ==========

    @commands.Cog.listener()
    async def on_ready(self):
        await on_ready(self.bot, self.read_channels, self._state)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await on_message(
            self.bot, message, self.read_channels,
            self.queues, self.is_processing, self.temp_dir, self.GLOBAL_DICT_ID
        )

    @commands.Cog.listener(name="on_voice_state_update")
    async def vc_notification(self, member, before, after):
        await on_voice_state_update_notification(
            self.bot, member, before, after,
            self.queues, self.is_processing, self.temp_dir
        )

    @commands.Cog.listener(name="on_voice_state_update")
    async def auto_join(self, member, before, after):
        await on_voice_state_update_auto_join(self.bot, member, before, after, self.read_channels)

    @commands.Cog.listener(name="on_voice_state_update")
    async def auto_leave(self, member, before, after):
        await on_voice_state_update_auto_leave(self.bot, member, before, after, self.read_channels)

    @commands.Cog.listener(name="on_voice_state_update")
    async def clear_on_leave(self, member, before, after):
        await on_voice_state_update_clear_on_leave(
            self.bot, member, before, after,
            self.read_channels, self.queues, self.is_processing
        )

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        await on_guild_remove(self.bot, guild)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await on_member_remove(self.bot, member)

    # ========== Slash Commands ==========

    @app_commands.command(name="join", description="ボイスチャンネルに接続し、このチャンネルを読み上げます")
    async def cmd_join(self, interaction: discord.Interaction):
        await join(self.bot, interaction, self.read_channels)

    @app_commands.command(name="leave", description="切断して読み上げを終了します")
    async def cmd_leave(self, interaction: discord.Interaction):
        await leave(self.bot, interaction, self.read_channels, self._delete_session_background)

    @app_commands.command(name="config", description="サーバーの読み上げ設定を表示・変更します")
    @app_commands.default_permissions(manage_guild=True)
    async def cmd_config(self, interaction: discord.Interaction):
        await config(self.bot, interaction)

    @app_commands.command(name="set_voice", description="自分の声をカスタマイズします")
    @app_commands.choices(speaker=[
        app_commands.Choice(name="四国めたん (ノーマル)", value=2),
        app_commands.Choice(name="四国めたん (あまあま)", value=0),
        app_commands.Choice(name="ずんだもん (ノーマル)", value=3),
        app_commands.Choice(name="ずんだもん (あまあま)", value=1),
        app_commands.Choice(name="春日部つむぎ", value=8),
        app_commands.Choice(name="雨晴はう", value=10),
        app_commands.Choice(name="波音リツ", value=9),
        app_commands.Choice(name="玄野武宏", value=11),
        app_commands.Choice(name="白上虎太郎", value=12),
        app_commands.Choice(name="青山龍星", value=13),
        app_commands.Choice(name="冥鳴ひまり", value=14),
        app_commands.Choice(name="九州そら (あまあま)", value=15),
        app_commands.Choice(name="もち子さん", value=20),
        app_commands.Choice(name="剣崎雌雄", value=21),
        app_commands.Choice(name="WhiteCUL", value=23),
        app_commands.Choice(name="後鬼", value=27),
        app_commands.Choice(name="No.7", value=29),
        app_commands.Choice(name="ちび式じい", value=42),
        app_commands.Choice(name="櫻歌ミコ", value=43),
        app_commands.Choice(name="小夜/SAYO", value=46),
        app_commands.Choice(name="ナースロボ＿タイプＴ", value=47),
        app_commands.Choice(name="聖騎士紅桜", value=50),
        app_commands.Choice(name="雀松朱司", value=52),
        app_commands.Choice(name="中国うさぎ", value=61),
        app_commands.Choice(name="春歌ナナ", value=54),
    ])
    @app_commands.describe(
        speaker="話者を選択してください",
        speed="話速（0.5〜2.0）",
        pitch="音高（-0.15〜0.15）"
    )
    async def cmd_set_voice(
        self,
        interaction: discord.Interaction,
        speaker: app_commands.Choice[int],
        speed: float = 1.0,
        pitch: float = 0.0
    ):
        await set_voice(self.bot, interaction, speaker.value, speaker.name, speed, pitch)

    @app_commands.command(name="dictionary", description="辞書を管理します")
    @app_commands.describe(
        action="実行する操作",
        word="登録/削除する単語",
        reading="読み方（カタカナ）"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="一覧表示", value="list"),
        app_commands.Choice(name="追加", value="add"),
        app_commands.Choice(name="削除", value="delete"),
    ])
    async def cmd_dictionary(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        word: str = None,
        reading: str = None
    ):
        words_dict = await get_guild_dict(self.bot, interaction)
        if words_dict is None:
            return

        if action.value == "list":
            await dictionary_list(self.bot, interaction, words_dict)
        elif action.value == "add":
            await dictionary_add(self.bot, interaction, words_dict, word, reading)
        elif action.value == "delete":
            await dictionary_delete(self.bot, interaction, words_dict, word)


async def setup(bot):
    await bot.add_cog(Voice(bot))
