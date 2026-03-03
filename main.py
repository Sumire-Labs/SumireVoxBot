import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import signal

# ロガー関連のインポート
from src.utils.logger import setup_logger, console
from rich.table import Table
from rich import box

from src.core.voicevox_client import VoicevoxClient
from src.core.database import Database

# ロガーのセットアップ
logger = setup_logger()

load_dotenv()

# インテントの設定
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

COMMAND_PREFIX: str = "!"
SYNC_KEY: str = "s"
QUIT_KEY: str = "q"
WEB_PORT: int = int(os.getenv("WEB_PORT", 8080))
VOICEVOX_HOST = os.getenv("VOICEVOX_HOST", "127.0.0.1")
VOICEVOX_PORT = int(os.getenv("VOICEVOX_PORT", 50021))
WEB_ENABLED: str = str(os.getenv("WEB_ENABLED", True))
DEV_GUILD_ID: int = int(os.getenv("DEV_GUILD_ID", 0))
COMMANDS_SYNC: str = str(os.getenv("COMMANDS_SYNC", True))
HOMEPAGE_DOMAIN: str = os.getenv("HOMEPAGE_DOMAIN", "sumirevox.com")

COGS: list[str] = [
    "src.cogs.voice",
    "src.cogs.commands",
    "src.cogs.boost"
]

# マルチインスタンス設定
MIN_BOOST_LEVEL = int(os.getenv("MIN_BOOST_LEVEL", "0"))


class SumireVox(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=COMMAND_PREFIX,
            intents=intents,
            help_command=None
        )
        self.web_task: asyncio.Task | None = None
        self.keystroke_task: asyncio.Task | None = None
        self.vv_client: VoicevoxClient | None = VoicevoxClient()
        self.db: Database | None = Database()

        # サブBotの場合は、インタラクションをサイレント無視するためのチェックを追加
        async def global_interaction_check(interaction: discord.Interaction) -> bool:
            if MIN_BOOST_LEVEL == 0:
                return True
            
            # サブBotの場合、そのサーバーでアクティブか確認
            if not interaction.guild_id:
                return False
            
            is_active = await self.db.is_instance_active(interaction.guild_id)
            # 非アクティブならサイレント無視 (False を返すとコマンドは実行されない)
            return is_active

        self.tree.interaction_check = global_interaction_check

    async def setup_hook(self) -> None:
        logger.info(f"初期化シーケンスを開始します... (MIN_BOOST_LEVEL: {MIN_BOOST_LEVEL})")

        loop = asyncio.get_event_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.close()))
            except NotImplementedError:
                pass

        try:
            await self.db.init_db()
            logger.success("データベースの初期化が完了しました")
        except Exception as e:
            logger.error(f"データベースの初期化に失敗しました: {e}")
            raise

        logger.info("Cogs の読み込みを開始します")
        # サブBotの場合、読み上げ以外のCog（Commands, Boost等）を読み込まないようにフィルタリング
        target_cogs = COGS
        if MIN_BOOST_LEVEL > 0:
            target_cogs = ["src.cogs.voice"]
            logger.info("サブBotモードのため、読み上げ用Cogのみを読み込みます")

        for cog in target_cogs:
            try:
                await self.load_extension(cog)
                logger.success(f"ロード: {cog}")
            except Exception as e:
                logger.error(f"{cog} の読み込みに失敗しました: {e}")

        if DEV_GUILD_ID != 0:
            try:
                logger.info(f"開発サーバー (ID: {DEV_GUILD_ID}) にコマンドを同期しています...")
                dev_guild = discord.Object(id=DEV_GUILD_ID)
                self.tree.copy_global_to(guild=dev_guild)
                synced = await self.tree.sync(guild=dev_guild)
                logger.success(f"{len(synced)}個のコマンドを開発サーバー (ID: {DEV_GUILD_ID}) に同期しました")
            except Exception as e:
                logger.error(f"開発サーバー (ID: {DEV_GUILD_ID}) のコマンド同期に失敗しました: {e}")
        else:
            try:
                logger.info(f"開発サーバーが指定されていないため、コマンドのグローバル同期を行います...")
                synced = await self.tree.sync(guild=None)
                logger.success(f"{len(synced)}個のコマンドを同期しました")
            except Exception as e:
                logger.error(f"コマンドのグローバル同期に失敗しました: {e}")

    async def close(self) -> None:
        logger.warning("シャットダウンシーケンスを開始します...")

        try:
            await self.vv_client.close()
            logger.success("VOICEVOX セッションを終了しました")
        except Exception as e:
            logger.error(f"VOICEVOXセッションの終了に失敗: {e}")

        try:
            await self.db.close()
            logger.success("データベース接続を終了しました")
        except Exception as e:
            logger.error(f"データベース接続の終了に失敗: {e}")

        await super().close()
        logger.success("Discord セッションを終了しました")

    async def on_ready(self) -> None:
        if hasattr(self, "_ready_logged"):
            return
        self._ready_logged = True

        await self._load_active_guild_dicts()

        # Activity の設定
        if MIN_BOOST_LEVEL == 0:
            activity = discord.Activity(name=f"{HOMEPAGE_DOMAIN} | 1台目", type=discord.ActivityType.playing)
        else:
            activity = discord.Activity(name=f"読み上げ専用 | {MIN_BOOST_LEVEL + 1}台目", type=discord.ActivityType.playing)
        await self.change_presence(activity=activity)

        # サブBotガード: メインBotがサーバーにいるか確認するタスクを開始
        if MIN_BOOST_LEVEL > 0:
            asyncio.create_task(self.main_bot_presence_check())

        # 起動時のステータスをテーブルで表示
        table = Table(
            title="🌸 SumireVox システム稼働状況",
            show_header=True,
            header_style="bold magenta",
            box=box.SQUARE
        )

        table.add_column("項目", style="cyan", no_wrap=True)
        table.add_column("ステータス / URL", style="white")

        table.add_row("ログインユーザー", f"{self.user} ({self.user.id})")
        table.add_row("インスタンス", f"{MIN_BOOST_LEVEL}台目 (Level: {MIN_BOOST_LEVEL})")
        table.add_row("接続サーバー数", f"{len(self.guilds)} guilds")

        console.print(table)
        logger.success("SumireVox は正常に起動し、待機中です。")

    async def main_bot_presence_check(self):
        """サブBot専用: メインBotが不在のサーバーで警告を出す（定期チェック）"""
        await self.wait_until_ready()
        main_bot_id = os.getenv("MAIN_BOT_ID")
        if not main_bot_id:
            logger.warning("MAIN_BOT_ID が未設定のため、メイン不在チェックをスキップします。")
            return

        while not self.is_closed():
            for guild in self.guilds:
                if not guild.get_member(int(main_bot_id)):
                    # メインBotがいない場合、ログを出力（必要に応じてサーバーに通知も可）
                    logger.warning(f"[{guild.id}] メインBotが不在です。サブBot({self.user.id})は正常に動作しない可能性があります。")
            await asyncio.sleep(3600)  # 1時間ごとにチェック

    async def _load_active_guild_dicts(self):
        """再起動時に既存のVC接続を復元し、辞書をロード"""
        for guild in self.guilds:
            if guild.voice_client and guild.voice_client.is_connected():
                logger.info(f"[{guild.id}] Restoring voice session after restart")
                await self.db.load_guild_dict(guild.id)

                # read_channelsの復元は難しいので、再接続が必要な旨をログに出す
                voice_cog = self.get_cog("Voice")
                if voice_cog and guild.id not in voice_cog.read_channels:
                    logger.warning(
                        f"[{guild.id}] Voice session restored but read channel unknown. "
                        f"Please use /leave and /join again."
                    )


if __name__ == "__main__":
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")

    if token:
        try:
            bot = SumireVox()
            bot.run(token, log_handler=None)  # 標準のロガーを無効化して loguru に一本化
        except Exception as e:
            logger.critical(f"Botの実行中に致命的なエラーが発生しました: {e}")
    else:
        logger.error("DISCORD_TOKEN が見つかりません。")
