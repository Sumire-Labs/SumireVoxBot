# src/cogs/voice/handlers/on_message.py
import discord
from loguru import logger

from ..validators.is_skip_command import is_skip_command
from ..validators.is_ignored_prefix import is_ignored_prefix
from ..text_processing.process_timestamp import process_timestamp
from ..text_processing.process_rendered_datetime import process_rendered_datetime
from ..text_processing.process_mentions import process_mentions
from ..text_processing.skip_code_blocks import skip_code_blocks
from ..text_processing.skip_urls import skip_urls
from ..text_processing.process_custom_emoji import process_custom_emoji
from ..text_processing.process_emoji import process_emoji
from ..text_processing.process_romaji import process_romaji
from ..text_processing.truncate_text import truncate_text
from ..text_processing.add_attachment_info import add_attachment_info
from ..dictionary.apply_dictionary import apply_dictionary
from ..audio.enqueue_message import enqueue_message
from ..constants.limits import DEFAULT_MAX_CHARS, BOOSTED_MAX_CHARS


async def on_message(
    bot,
    message: discord.Message,
    read_channels: dict,
    queues: dict,
    is_processing: dict,
    temp_dir: str,
    global_dict_id: int
) -> None:
    if message.author.bot or not message.guild or not message.guild.voice_client:
        return

    if message.channel.id != read_channels.get(message.guild.id):
        return

    guild_id = message.guild.id

    # スキップコマンド
    if is_skip_command(message.content):
        if message.guild.voice_client.is_playing():
            message.guild.voice_client.stop()
            logger.info(f"[{guild_id}] 再生中断: {message.author.display_name}")
        return

    # 無視するプレフィックス
    if is_ignored_prefix(message.content):
        return

    # インスタンスアクティブ判定
    is_active = await bot.db.is_instance_active(guild_id)
    if not is_active:
        return

    settings = await bot.db.get_guild_settings(guild_id)
    is_boosted = await bot.db.is_guild_boosted(guild_id)

    max_chars = min(settings.max_chars, BOOSTED_MAX_CHARS) if is_boosted else DEFAULT_MAX_CHARS

    content = message.clean_content

    # テキスト処理パイプライン
    content = process_timestamp(content)
    content = process_rendered_datetime(content)

    if settings.read_mention:
        content = process_mentions(content, message.mentions)

    if settings.skip_code_blocks:
        content = skip_code_blocks(content)

    if settings.skip_urls:
        content = skip_urls(content)

    content = process_custom_emoji(content)
    content = process_emoji(content, settings.read_emoji)

    # 辞書適用
    content = await apply_dictionary(bot, content, guild_id)

    if global_dict_id and global_dict_id != 0:
        content = await apply_dictionary(bot, content, global_dict_id)

    # ローマ字変換
    if settings.read_romaji:
        content = process_romaji(content)

    # 長文切り詰め
    content = truncate_text(content, max_chars)

    # 添付ファイル
    if settings.read_attachments:
        content = add_attachment_info(content, len(message.attachments))

    if not content.strip():
        return

    await enqueue_message(bot, queues, is_processing, temp_dir, guild_id, content, message.author.id)
