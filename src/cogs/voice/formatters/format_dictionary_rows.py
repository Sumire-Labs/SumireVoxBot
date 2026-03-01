# src/cogs/voice/formatters/format_dictionary_rows.py
from loguru import logger


def format_dictionary_rows(rows) -> str:
    if not rows:
        return "登録なし"
    try:
        if isinstance(rows, dict):
            return "\n".join([f"・`{word}` → `{reading}`" for word, reading in rows.items()])
        return "\n".join([f"・`{r['word']}` → `{r['reading']}`" for r in rows])
    except (KeyError, TypeError) as e:
        logger.error(f"辞書データのフォーマットエラー: {e}")
        return "データ形式エラー"
