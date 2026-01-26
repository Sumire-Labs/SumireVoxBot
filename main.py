import asyncio
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from aioconsole import ainput

# ロガー関連のインポート
from src.utils.logger import setup_logger, console
from rich.table import Table
from rich import box

from src.core.voicevox_client import VoicevoxClient
from src.core.database import Database
from src.web.web_admin import run_web_admin

# ロガーのセットアップ
logger = setup_logger()

# インテントの設定
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

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
        self.vv_client = VoicevoxClient()
        self.db = Database()

    async def setup_hook(self) -> None:
        logger.info("初期化シーケンスを開始します...")

        await self.db.init_db()
        # Web管理画面のタスク開始
        asyncio.create_task(run_web_admin(self.vv_client))

        logger.info("Cogs の読み込みを開始します")
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.success(f"Loaded: {cog}")
            except Exception as e:
                logger.error(f"Failed to load {cog}: {e}")

        asyncio.create_task(self.watch_keystroke())
        logger.info("キーボード入力を監視中: 's' キー + Enter でコマンドを同期します")

    async def watch_keystroke(self):
        """ターミナルからの入力を監視するタスク"""
        while True:
            # 入力を非同期で待機
            line = await ainput()
            if line.strip().lower() == 's':
                logger.info("サーバー側からのリクエストにより同期を開始します...")
                try:
                    synced = await self.tree.sync()
                    logger.success(f"{len(synced)} 個のコマンドを同期しました！")
                except Exception as e:
                    logger.error(f"同期エラー: {e}")
            elif line.strip().lower() == 'q':
                logger.warning("終了コマンドを受信しました。Botを停止します。")
                await self.close()
                break

    async def close(self) -> None:
        logger.warning("シャットダウンシーケンスを開始します...")
        await self.vv_client.close()
        logger.success("VOICEVOX セッションを終了しました")
        await self.db.close()
        logger.success("データベース接続を終了しました")
        await super().close()
        logger.success("Discord セッションを終了しました")

    async def on_ready(self) -> None:
        web_port = os.getenv("WEB_ADMIN_PORT", "8080")
        web_url = f"http://localhost:{web_port}"

        vv_host = os.getenv("VOICEVOX_HOST", "127.0.0.1")
        vv_port = os.getenv("VOICEVOX_PORT", "50021")
        vv_url = f"http://{vv_host}:{vv_port}"

        # 起動時のステータスをテーブルで表示
        table = Table(
            title="🌸 SumireVox システム稼働状況",
            show_header=True,
            header_style="bold magenta",
            box=box.SQUARE  # これで枠線のガタつきを防止します
        )

        table.add_column("項目", style="cyan", no_wrap=True)
        table.add_column("ステータス / URL", style="white")

        table.add_row("ログインユーザー", f"{self.user} ({self.user.id})")
        table.add_row("接続サーバー数", f"{len(self.guilds)} guilds")

        # 管理画面とエンジンの情報を表示
        table.add_row("Web管理画面", f"[link={web_url}]{web_url}[/link] (User: {os.getenv('ADMIN_USER')})")
        table.add_row("VOICEVOX Engine", f"[link={vv_url}]{vv_url}[/link]")
        table.add_row("外部アクセス", "[yellow]無効 (Localhost Only)[/yellow]")

        console.print(table)
        logger.success("SumireVox は正常に起動し、待機中です。")


bot = SumireVox()


@bot.command()
@commands.is_owner()
async def sync(ctx):
    logger.info("手動同期リクエストを受信しました")
    synced = await bot.tree.sync()
    await ctx.send(f"Successfully synced {len(synced)} commands.")
    logger.success(f"{len(synced)} 個のコマンドを同期しました")


if __name__ == "__main__":
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")

    if token:
        try:
            bot.run(token, log_handler=None)  # 標準のロガーを無効化して loguru に一本化
        except Exception as e:
            logger.critical(f"Botの実行中に致命的なエラーが発生しました: {e}")
    else:
        logger.error(".env ファイルに DISCORD_TOKEN が見つかりません。")
