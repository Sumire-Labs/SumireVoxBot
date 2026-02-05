import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import signal
import uvicorn

# ロガー関連のインポート
from src.utils.logger import setup_logger, console
from rich.table import Table
from rich import box

from src.core.voicevox_client import VoicevoxClient
from src.core.database import Database
from src.web.web import app as web_app

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

COGS: list[str] = [
    "src.cogs.voice",
    "src.cogs.commands"
]


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

    async def setup_hook(self) -> None:
        logger.info("初期化シーケンスを開始します...")

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
        for cog in COGS:
            try:
                await self.load_extension(cog)
                logger.success(f"ロード: {cog}")
            except Exception as e:
                logger.error(f"{cog} の読み込みに失敗しました: {e}")

        try:
            config = uvicorn.Config(web_app, host="0.0.0.0", port=WEB_PORT, log_level="error", loop="asyncio")
            server = uvicorn.Server(config)
            self.web_task = asyncio.create_task(server.serve())
            logger.success(f"Web管理画面をポート {WEB_PORT} で起動しました")
        except OSError as e:
            logger.error(f"Web管理画面の起動に失敗しました (ポート {WEB_PORT} が使用中の可能性があります): {e}")
            raise
        except Exception as e:
            logger.error(f"Web管理画面の起動中に予期しないエラーが発生しました: {e}")
            raise

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

        try:
            if self.web_task:
                self.web_task.cancel()
                logger.success(f"Web管理画面を終了しました")
        except Exception as e:
            logger.error(f"Web管理画面の終了に失敗: {e}")

        await super().close()
        logger.success("Discord セッションを終了しました")

    async def on_ready(self) -> None:
        if hasattr(self, "_ready_logged"):
            return
        _ready_logged = True

        vv_url = f"http://{VOICEVOX_HOST}:{VOICEVOX_PORT}"
        web_url = f"http://localhost:{WEB_PORT}"

        admin_user = os.getenv("ADMIN_USER", "Not Configured")

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
        table.add_row("接続サーバー数", f"{len(self.guilds)} guilds")

        # エンジンの情報を表示
        table.add_row("VOICEVOX Engine", f"[link={vv_url}]{vv_url}[/link]")
        table.add_row("WEB管理画面", f"[link={web_url}]{web_url}[/link]")

        console.print(table)
        logger.success("SumireVox は正常に起動し、待機中です。")


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
        logger.error(".env ファイルに DISCORD_TOKEN が見つかりません。")
