from loguru import logger
from rich.logging import RichHandler
from rich.console import Console
import sys
import os

# Richのコンソール初期化
console = Console()


def setup_logger():
    # 既存のハンドラを削除
    logger.remove()

    # 1. コンソール出力 (RichHandlerを使用)
    # これにより、ログの中にRichのテーブルや色付けが反映されるようになります
    logger.add(
        RichHandler(rich_tracebacks=True, markup=True),
        format="{message}",
        level="INFO"
    )

    # 2. ファイル出力 (Loguru標準)
    if not os.path.exists("logs"):
        os.makedirs("logs")

    logger.add(
        "logs/bot.log",
        rotation="1 MB",
        retention="10 days",
        compression="zip",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level="DEBUG",
        encoding="utf-8"
    )

    return logger