# src/cogs/voice.py

import discord
import emoji
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import re
import jaconv
from loguru import logger
import romkan2
from dotenv import load_dotenv
from src.utils.views import ConfigSearchView, DictionaryView, create_dictionary_embed
import uuid
from dataclasses import dataclass, field

AUTO_LEAVE_INTERVAL: int = 1
DISCONNECT_CONFIRM_DELAY: int = 30


def is_katakana(text: str) -> bool:
    """全角カタカナ、長音記号のみで構成されているか判定"""
    return re.fullmatch(r'^[ァ-ヶーヴ]+$', text) is not None


def format_rows(rows):
    if not rows:
        return "登録なし"
    try:
        if isinstance(rows, dict):
            return "\n".join([f"・`{word}` → `{reading}`" for word, reading in rows.items()])
        return "\n".join([f"・`{r['word']}` → `{r['reading']}`" for r in rows])
    except (KeyError, TypeError) as e:
        logger.error(f"辞書データのフォーマットエラー: {e}")
        return "データ形式エラー"


@dataclass
class AudioTask:
    """音声生成タスクを管理するデータクラス"""
    task_id: str
    text: str
    author_id: int
    file_path: str
    generation_task: asyncio.Task = field(default=None, repr=False)
    is_ready: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    is_failed: bool = False


# noinspection PyUnresolvedReferences
class Voice(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.temp_dir = "temp"
        self.queues: dict[int, asyncio.Queue[AudioTask]] = {}
        self.is_processing = {}
        self.read_channels = {}

        load_dotenv()
        self.GLOBAL_DICT_ID = int(os.getenv("GLOBAL_DICT_ID", "0"))

        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
            logger.info(f"一時ディレクトリを作成しました: {self.temp_dir}")

    # ========================================
    # 起動時のセッション復元
    # ========================================

    @commands.Cog.listener()
    async def on_ready(self):
        """Bot起動時にDBからセッションを復元する"""
        # 重複呼び出し防止
        if hasattr(self, "_session_restore_done"):
            return
        self._session_restore_done = True

        # Botが完全に準備できるまで少し待機
        await asyncio.sleep(2)

        await self._restore_voice_sessions()

    async def _restore_voice_sessions(self):
        """DBに保存されたセッションを復元してVCに再接続する"""
        logger.info("Restoring voice sessions from database...")

        try:
            sessions = await self.bot.db.get_voice_sessions_by_bot(self.bot.user.id)
        except Exception as e:
            logger.error(f"Failed to fetch voice sessions from DB: {e}")
            return

        if not sessions:
            logger.info("No voice sessions to restore.")
            return

        logger.info(f"Found {len(sessions)} session(s) to restore.")

        restored_count = 0
        failed_count = 0

        for session in sessions:
            guild_id = session["guild_id"]
            voice_channel_id = session["voice_channel_id"]
            text_channel_id = session["text_channel_id"]

            result = await self._try_restore_session(guild_id, voice_channel_id, text_channel_id)

            if result:
                restored_count += 1
            else:
                failed_count += 1
                # 復元に失敗したセッションはDBから削除（バックグラウンド）
                asyncio.create_task(self._delete_session_background(guild_id))

        logger.success(
            f"Voice session restoration complete: "
            f"{restored_count} restored, {failed_count} skipped/failed"
        )

    async def _delete_session_background(self, guild_id: int):
        """バックグラウンドでセッションを削除"""
        try:
            await self.bot.db.delete_voice_session(guild_id)
        except Exception as e:
            logger.error(f"[{guild_id}] Failed to delete voice session: {e}")

    async def _try_restore_session(
        self,
        guild_id: int,
        voice_channel_id: int,
        text_channel_id: int
    ) -> bool:
        """
        単一のセッションを復元する

        Returns:
            bool: 復元成功ならTrue、失敗/スキップならFalse
        """
        try:
            # ギルドの取得
            guild = self.bot.get_guild(guild_id)
            if not guild:
                logger.warning(f"[{guild_id}] Restore skipped: Guild not found")
                return False

            # ボイスチャンネルの取得
            voice_channel = guild.get_channel(voice_channel_id)
            if not voice_channel:
                logger.warning(f"[{guild_id}] Restore skipped: Voice channel {voice_channel_id} not found")
                return False

            # ボイスチャンネルかどうか確認
            if not isinstance(voice_channel, (discord.VoiceChannel, discord.StageChannel)):
                logger.warning(f"[{guild_id}] Restore skipped: Channel {voice_channel_id} is not a voice channel")
                return False

            # テキストチャンネルの取得
            text_channel = guild.get_channel(text_channel_id)
            if not text_channel:
                logger.warning(f"[{guild_id}] Restore skipped: Text channel {text_channel_id} not found")
                return False

            # テキストチャンネルかどうか確認
            if not isinstance(text_channel, discord.TextChannel):
                logger.warning(f"[{guild_id}] Restore skipped: Channel {text_channel_id} is not a text channel")
                return False

            # ボイスチャンネルに人間がいるか確認
            human_members = [m for m in voice_channel.members if not m.bot]
            if not human_members:
                logger.info(f"[{guild_id}] Restore skipped: No human members in voice channel")
                return False

            # 既に接続中か確認
            if guild.voice_client and guild.voice_client.is_connected():
                logger.info(f"[{guild_id}] Restore skipped: Already connected to a voice channel")
                # read_channelsだけ復元
                self.read_channels[guild_id] = text_channel_id
                await self.bot.db.load_guild_dict(guild_id)
                return True

            # 他のSumireVox系Botがいないか確認
            other_bot = discord.utils.find(
                lambda m: m.bot and m.id != self.bot.user.id and ("Sumire" in m.name or "Vox" in m.name),
                voice_channel.members
            )
            if other_bot:
                logger.info(
                    f"[{guild_id}] Restore skipped: Another SumireVox bot ({other_bot.display_name}) "
                    f"is already in the channel"
                )
                return False

            # 接続権限の確認
            permissions = voice_channel.permissions_for(guild.me)
            if not permissions.connect or not permissions.speak:
                logger.warning(f"[{guild_id}] Restore skipped: Missing permissions to connect/speak")
                return False

            # 接続を試行
            try:
                await voice_channel.connect(timeout=10.0)
            except asyncio.TimeoutError:
                logger.warning(f"[{guild_id}] Restore failed: Connection timeout")
                return False
            except discord.errors.ClientException as e:
                logger.warning(f"[{guild_id}] Restore failed: {e}")
                return False

            # 変数に保存
            self.read_channels[guild_id] = text_channel_id

            # 辞書をロード
            await self.bot.db.load_guild_dict(guild_id)

            logger.success(
                f"[{guild_id}] Session restored: "
                f"VC={voice_channel.name}, TC={text_channel.name}"
            )

            # 復元通知を送信（オプション）
            try:
                embed = discord.Embed(
                    title="🔄 再接続しました",
                    description=(
                        f"Botの再起動により **{voice_channel.name}** に再接続しました。\n"
                        f"読み上げを再開します。"
                    ),
                    color=discord.Color.blue()
                )
                await text_channel.send(embed=embed)
            except discord.errors.Forbidden:
                logger.warning(f"[{guild_id}] Could not send restore notification (no permission)")
            except Exception as e:
                logger.warning(f"[{guild_id}] Could not send restore notification: {e}")

            return True

        except Exception as e:
            logger.error(f"[{guild_id}] Restore failed with unexpected error: {e}")
            return False

    # ========================================
    # キュー管理
    # ========================================

    def get_queue(self, guild_id: int) -> asyncio.Queue[AudioTask]:
        if guild_id not in self.queues:
            self.queues[guild_id] = asyncio.Queue()
            self.is_processing[guild_id] = False
        return self.queues[guild_id]

    async def apply_dictionary(self, content: str, guild_id: int) -> str:
        """辞書を適用してテキストを変換する"""
        if not guild_id or guild_id == 0:
            return content

        words = await self.bot.db.get_dict(guild_id)
        if words and isinstance(words, dict):
            for word in sorted(words.keys(), key=len, reverse=True):
                word_str = str(word)
                pattern = re.compile(re.escape(word_str), re.IGNORECASE)
                content = pattern.sub(str(words[word]), content)
        return content

    async def _get_guild_dict(self, interaction: discord.Interaction) -> dict | None:
        """ギルドの辞書を取得する共通ヘルパー。エラー時はユーザーに応答を返し None を戻す"""
        try:
            words_dict = await self.bot.db.get_dict(interaction.guild.id)
            return words_dict if isinstance(words_dict, dict) else {}
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書の取得に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ 辞書の取得エラー",
                description="辞書の取得中にエラーが発生しました。",
                color=discord.Color.red()
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(embed=embed, ephemeral=True)
            return None

    # ========================================
    # 音声生成・再生
    # ========================================

    async def _generate_audio(self, audio_task: AudioTask, guild_id: int):
        """音声ファイルを生成する（バックグラウンドタスク）"""
        try:
            # DBからユーザー設定を読み込む
            try:
                s = await self.bot.db.get_user_setting(audio_task.author_id)
            except Exception as e:
                logger.error(f"[{guild_id}] ユーザー設定の取得に失敗しました (user_id: {audio_task.author_id}): {e}")
                s = {"speaker": 1, "speed": 1.0, "pitch": 0.0}

            is_boosted = await self.bot.db.is_guild_boosted(guild_id)
            if not is_boosted:
                s["speed"] = 1.0
                s["pitch"] = 0.0

            # 正規化処理
            try:
                normalized_text = jaconv.h2z(audio_task.text, kana=True, digit=True, ascii=True).lower()
                logger.debug(f"[{guild_id}] 音声生成開始 ({audio_task.task_id}): {normalized_text[:20]}...")
            except Exception as e:
                logger.error(f"[{guild_id}] テキストの正規化に失敗しました: {e}")
                audio_task.is_failed = True
                audio_task.is_ready.set()
                return

            # 音声生成
            try:
                await self.bot.vv_client.generate_sound(
                    text=normalized_text,
                    speaker_id=s["speaker"],
                    speed=s["speed"],
                    pitch=s["pitch"],
                    output_path=audio_task.file_path
                )
                logger.debug(f"[{guild_id}] 音声生成完了 ({audio_task.task_id})")
            except Exception as e:
                logger.error(f"[{guild_id}] 音声生成に失敗しました ({audio_task.task_id}): {e}")
                audio_task.is_failed = True
                audio_task.is_ready.set()
                return

            # ファイルが正常に生成されたか確認
            if not os.path.exists(audio_task.file_path):
                logger.error(f"[{guild_id}] 音声ファイルが生成されませんでした: {audio_task.file_path}")
                audio_task.is_failed = True

            audio_task.is_ready.set()

        except asyncio.CancelledError:
            logger.warning(f"[{guild_id}] 音声生成タスクがキャンセルされました ({audio_task.task_id})")
            audio_task.is_failed = True
            audio_task.is_ready.set()
            # キャンセル時もファイルがあれば削除
            if os.path.exists(audio_task.file_path):
                try:
                    os.remove(audio_task.file_path)
                except Exception:
                    pass
            raise
        except Exception as e:
            logger.error(f"[{guild_id}] 音声生成中に予期しないエラー ({audio_task.task_id}): {e}")
            audio_task.is_failed = True
            audio_task.is_ready.set()

    async def enqueue_message(self, guild_id: int, text: str, author_id: int):
        """メッセージをキューに追加し、音声生成を開始する"""
        logger.debug(f"[DEBUG] enqueue_message(guild_id={guild_id}, author_id={author_id}) text='{text[:50]}'")
        task_id = str(uuid.uuid4())
        file_path = f"{self.temp_dir}/audio_{guild_id}_{task_id}.wav"

        audio_task = AudioTask(
            task_id=task_id,
            text=text,
            author_id=author_id,
            file_path=file_path
        )

        # 音声生成タスクをバックグラウンドで開始
        audio_task.generation_task = asyncio.create_task(
            self._generate_audio(audio_task, guild_id)
        )

        # キューに追加
        queue = self.get_queue(guild_id)
        await queue.put(audio_task)

        logger.debug(f"[{guild_id}] キューに追加 ({task_id}): {text[:20]}...")

        # 再生処理が動いていなければ開始
        if not self.is_processing[guild_id]:
            asyncio.create_task(self.play_next(guild_id))

    async def play_next(self, guild_id: int):
        self.is_processing[guild_id] = True
        queue = self.get_queue(guild_id)
        guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)
        vc = guild.voice_client
        logger.debug(
            f"[DEBUG] play_next start guild={guild_id}, vc_connected={bool(vc and vc.is_connected())}, queue_size={queue.qsize()}")

        try:
            while not queue.empty():
                audio_task: AudioTask = await queue.get()
                try:
                    await self._play_audio_task(guild, audio_task)
                except Exception as e:
                    logger.error(f"[{guild_id}] 再生中にエラーが発生しました: {e}")
                finally:
                    queue.task_done()
                    # 一時ファイルのクリーンアップ
                    await self._cleanup_audio_file(audio_task, guild_id)
        finally:
            self.is_processing[guild_id] = False

    async def _play_audio_task(self, guild, audio_task: AudioTask):
        """AudioTaskを再生する"""
        guild_id = guild.id

        # 音声生成の完了を待機（タイムアウト付き）
        try:
            await asyncio.wait_for(audio_task.is_ready.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            logger.warning(f"[{guild_id}] 音声生成がタイムアウトしました ({audio_task.task_id})")
            return

        # 生成に失敗していた場合はスキップ
        if audio_task.is_failed:
            logger.warning(f"[{guild_id}] 音声生成が失敗したためスキップ ({audio_task.task_id})")
            return

        # 生成ファイルの存在確認
        if not os.path.exists(audio_task.file_path):
            logger.error(f"[{guild_id}] 生成ファイルが見つかりません: {audio_task.file_path}")
            return

        # ボイスチャットに接続していない場合はスキップ
        if not guild.voice_client:
            logger.warning(f"[{guild_id}] VC未接続のため再生をスキップしました ({audio_task.task_id})")
            return

        # 再生処理
        try:
            if not guild.voice_client or not guild.voice_client.is_connected():
                logger.error(f"[{guild_id}] VC切断を検知したため、再接続を試みます...")
                return

            logger.debug(
                f"[DEBUG] 再生開始: file={audio_task.file_path}, vc_connected={guild.voice_client.is_connected()}")
            source = discord.FFmpegPCMAudio(
                audio_task.file_path,
                options="-vn -loglevel quiet",
                before_options="-loglevel quiet",
            )
            stop_event = asyncio.Event()

            def after_callback(error):
                if error:
                    logger.error(f"[{guild_id}] 再生中にエラーが発生しました (callback): {error}")
                if self.bot.loop.is_running():
                    self.bot.loop.call_soon_threadsafe(stop_event.set)

            guild.voice_client.play(source, after=after_callback)

            # タイムアウト付きで待機（30秒）
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=35.0)
                logger.info(f"[{guild_id}] 再生完了 ({audio_task.task_id}): {audio_task.text[:15]}")
            except asyncio.TimeoutError:
                logger.warning(f"[{guild_id}] 再生がタイムアウトしました ({audio_task.task_id})")
                if guild.voice_client and guild.voice_client.is_playing():
                    guild.voice_client.stop()
            except Exception as e:
                logger.error(f"[{guild_id}] 再生待機中に予期しないエラーが発生しました: {e}")

        except discord.errors.ClientException as e:
            logger.error(f"[{guild_id}] Discord再生エラー (ClientException): {e}")
            if guild.voice_client and not guild.voice_client.is_playing():
                try:
                    await guild.voice_client.disconnect(force=True)
                except:
                    pass
        except Exception as e:
            logger.error(f"[{guild_id}] 再生処理中に予期しないエラーが発生しました: {e}")

    async def _cleanup_audio_file(self, audio_task: AudioTask, guild_id: int):
        """音声ファイルを削除する"""
        try:
            if os.path.exists(audio_task.file_path):
                await asyncio.sleep(0.5)
                os.remove(audio_task.file_path)
                logger.debug(f"[{guild_id}] 一時ファイルを削除しました: {audio_task.file_path}")
        except Exception as e:
            logger.warning(f"[{guild_id}] 一時ファイルの削除に失敗しました: {e}")

    # ========================================
    # イベントリスナー
    # ========================================

    @commands.Cog.listener(name="on_voice_state_update")
    async def on_vc_notification(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """ユーザーの入退出を検知して読み上げる"""
        try:
            if member.bot or not member.guild.voice_client:
                return

            bot_vc = member.guild.voice_client.channel

            try:
                settings = await self.bot.db.get_guild_settings(member.guild.id)
            except Exception as e:
                logger.error(f"[{member.guild.id}] サーバー設定の取得に失敗しました: {e}")
                return

            if not settings.read_vc_status:
                return

            content = None
            if before.channel != bot_vc and after.channel == bot_vc:
                suffix = "さん" if settings.add_suffix else ""
                content = f"{member.display_name}{suffix}が入室しました"
            elif before.channel == bot_vc and after.channel != bot_vc:
                suffix = "さん" if settings.add_suffix else ""
                content = f"{member.display_name}{suffix}が退室しました"

            if content:
                try:
                    await self.enqueue_message(member.guild.id, content, member.id)
                except Exception as e:
                    logger.error(f"[{member.guild.id}] VC通知のキューイングに失敗しました: {e}")
        except Exception as e:
            logger.error(f"[{member.guild.id}] VC通知処理中にエラーが発生しました: {e}")

    @commands.Cog.listener(name="on_message")
    async def read_message(self, message: discord.Message):
        if message.author.bot:
            return

        if not message.guild:
            return

        if not message.guild.voice_client:
            return

        if message.channel.id != self.read_channels.get(message.guild.id):
            return

        logger.debug(
            f"on_message received in {message.guild.name} from {message.author.display_name}: {message.content[:50]}")

        # 「s」または「ｓ」一文字なら読み上げ中断
        if message.content.strip() in ("s", "ｓ"):
            if message.guild.voice_client.is_playing():
                message.guild.voice_client.stop()
                logger.info(f"[{message.guild.id}] ユーザーにより再生が中断されました: {message.author.display_name}")
                return

        if message.content.startswith(("!", "！")):
            return

        # インスタンスのアクティブ判定
        is_active = await self.bot.db.is_instance_active(message.guild.id)
        if not is_active:
            logger.debug(f"Instance is NOT active for guild {message.guild.id}. Skipping message.")
            return

        settings = await self.bot.db.get_guild_settings(message.guild.id)
        is_boosted = await self.bot.db.is_guild_boosted(message.guild.id)

        if is_boosted:
            max_chars = min(settings.max_chars, 200)
        else:
            max_chars = 50

        logger.debug(f"Processing message. is_boosted={is_boosted}, max_chars={max_chars}")

        content = message.clean_content

        # Discordのタイムスタンプ表現を読み上げ用に変換
        def _format_discord_timestamp_for_tts(match: re.Match) -> str:
            try:
                unix = int(match.group("unix"))
            except Exception:
                return match.group(0)

            fmt = match.group("fmt") or "f"

            from datetime import datetime, timezone

            dt = datetime.fromtimestamp(unix, tz=timezone.utc)
            now = datetime.now(timezone.utc)

            def _relative_jp(target: datetime, base: datetime) -> str:
                delta_sec = int((target - base).total_seconds())
                future = delta_sec > 0
                sec = abs(delta_sec)

                if sec < 60:
                    n, unit = sec, "秒"
                elif sec < 3600:
                    n, unit = sec // 60, "分"
                elif sec < 86400:
                    n, unit = sec // 3600, "時間"
                elif sec < 86400 * 30:
                    n, unit = sec // 86400, "日"
                elif sec < 86400 * 365:
                    n, unit = sec // (86400 * 30), "か月"
                else:
                    n, unit = sec // (86400 * 365), "年"

                if n <= 0:
                    n = 1

                return f"{n}{unit}{'後' if future else '前'}"

            if fmt == "R":
                return _relative_jp(dt, now)

            local_dt = dt.astimezone()

            if fmt == "t":
                return f"{local_dt.hour}時{local_dt.minute}分"
            if fmt == "T":
                return f"{local_dt.hour}時{local_dt.minute}分{local_dt.second}秒"
            if fmt == "d":
                return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日"
            if fmt == "D":
                return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日"
            if fmt == "f":
                return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日{local_dt.hour}時{local_dt.minute}分"
            if fmt == "F":
                return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日{local_dt.hour}時{local_dt.minute}分"
            if fmt == "S":
                return (
                    f"{local_dt.year}年{local_dt.month}月{local_dt.day}日"
                    f"{local_dt.hour}時{local_dt.minute}分{local_dt.second}秒"
                )

            return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日{local_dt.hour}時{local_dt.minute}分"

        content = re.sub(
            r"<t:(?P<unix>\d+)(?::(?P<fmt>[A-Za-z]))?>",
            _format_discord_timestamp_for_tts,
            content
        )

        def _format_rendered_datetime_for_tts(match: re.Match) -> str:
            y = int(match.group("y"))
            mo = int(match.group("mo"))
            d = int(match.group("d"))
            hh = int(match.group("hh"))
            mm = int(match.group("mm"))
            ss = int(match.group("ss"))
            return f"{y}年{mo}月{d}日{hh}時{mm}分{ss}秒"

        content = re.sub(
            r"(?P<y>\d{4})/(?P<mo>\d{2})/(?P<d>\d{2})[ ](?P<hh>\d{2}):(?P<mm>\d{2}):(?P<ss>\d{2})",
            _format_rendered_datetime_for_tts,
            content
        )

        # メンション読み上げ
        if settings.read_mention:
            for mention in message.mentions:
                content = content.replace(f"@{mention.display_name}", f"メンション{mention.display_name}")

        # コードブロックを省略
        if settings.skip_code_blocks:
            content = re.sub(r"```.*?```", "、コードブロック省略、", content, flags=re.DOTALL)
            content = re.sub(r"`.*?`", "、コード省略、", content, flags=re.DOTALL)

        # URLを省略
        if settings.skip_urls:
            content = re.sub(r"https?://[\w/:%#$&?()~.=+\-]+", "、ユーアールエル省略、", content)

        # サーバー絵文字の処理
        content = re.sub(r"<a?:(\w+):?\d+>", r"\1", content)

        # 絵文字の読み上げ
        if settings.read_emoji:
            content = emoji.demojize(content, language="ja")
            content = content.replace(":", "、")
        else:
            content = emoji.replace_emoji(content, "")

        # 辞書適応
        content = await self.apply_dictionary(content, message.guild.id)

        # グローバル辞書
        if self.GLOBAL_DICT_ID and self.GLOBAL_DICT_ID != 0:
            content = await self.apply_dictionary(content, self.GLOBAL_DICT_ID)

        # ローマ字を仮名読みに変換
        if settings.read_romaji:
            content = romkan2.to_hiragana(content)

        # 長文対策
        if len(content) > max_chars:
            content = content[:max_chars]
            content = content + "、以下略"

        # 添付ファイルのチェック
        if settings.read_attachments:
            if message.attachments:
                content += f"、{len(message.attachments)}件の添付ファイル"

        if not content.strip():
            return

        await self.enqueue_message(message.guild.id, content, message.author.id)

    @commands.Cog.listener(name="on_voice_state_update")
    async def clear_info_on_leave(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Bot自身がVCから切断されたら情報をクリアする"""

        def _is_bot_disconnect() -> bool:
            return (
                member.id == self.bot.user.id
                and before.channel is not None
                and after.channel is None
            )

        async def _cancel_generation_task(audio_task: AudioTask, guild_id: int) -> None:
            task = audio_task.generation_task
            if not task or task.done():
                return

            try:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            except Exception as e:
                logger.error(f"[{guild_id}] タスクキャンセル中にエラーが発生しました: {e}")

        def _delete_audio_file(audio_task: AudioTask, guild_id: int) -> None:
            file_path = audio_task.file_path
            if not file_path or not os.path.exists(file_path):
                return

            try:
                os.remove(file_path)
                logger.debug(f"[{guild_id}] 一時ファイルを削除しました: {file_path}")
            except PermissionError as e:
                logger.warning(f"[{guild_id}] ファイル削除の権限エラー: {e}")
            except OSError as e:
                logger.warning(f"[{guild_id}] ファイル削除中にOSエラーが発生しました: {e}")
            except Exception as e:
                logger.error(f"[{guild_id}] ファイル削除中に予期しないエラーが発生しました: {e}")

        def _is_reconnected(guild_id: int) -> bool:
            guild = self.bot.get_guild(guild_id)
            vc = guild.voice_client if guild else None
            return bool(vc and vc.is_connected())

        async def _cleanup_queue(guild_id: int) -> None:
            queue = self.queues.get(guild_id)
            if not queue:
                return

            while True:
                try:
                    audio_task: AudioTask = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                except Exception as e:
                    logger.error(f"[{guild_id}] キューのクリーンアップ中にエラーが発生しました: {e}")
                    continue

                await _cancel_generation_task(audio_task, guild_id)
                _delete_audio_file(audio_task, guild_id)

            try:
                del self.queues[guild_id]
                self.is_processing.pop(guild_id, None)
            except Exception as e:
                logger.error(f"[{guild_id}] キューオブジェクトの削除中にエラーが発生しました: {e}")

        if not _is_bot_disconnect():
            return

        guild_id = member.guild.id

        try:
            logger.info(f"[{guild_id}] VC切断を検知しました。{DISCONNECT_CONFIRM_DELAY}秒後に再確認します...")
            await asyncio.sleep(DISCONNECT_CONFIRM_DELAY)

            if _is_reconnected(guild_id):
                logger.info(f"[{guild_id}] 再接続を確認しました。キャッシュのクリアをスキップします。")
                return

            logger.warning(f"[{guild_id}] VC切断を確認したため、キューをクリアします。")

            # 変数から削除
            self.read_channels.pop(guild_id, None)

            # 辞書をアンロード
            await self.bot.db.unload_guild_dict(guild_id)

            # キューのクリーンアップ
            await _cleanup_queue(guild_id)

            # DBからセッションを削除（バックグラウンド）
            asyncio.create_task(self._delete_session_background(guild_id))

            logger.warning(f"[{guild_id}] VC切断を検知したため、キューをクリアしました。")

        except asyncio.CancelledError:
            logger.warning(f"[{guild_id}] クリーンアップ処理がキャンセルされました")
            raise
        except Exception as e:
            logger.error(f"[{guild_id}] VC切断時のクリーンアップ中に予期しないエラーが発生しました: {e}")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        """Botがサーバーを脱退/蹴られた際にブースト情報をクリーンアップする"""
        try:
            await self.bot.db.delete_guild_boosts_by_guild(guild.id)
            logger.info(f"[{guild.id}] サーバー脱退に伴いブースト情報を削除しました。")
        except Exception as e:
            logger.error(f"[{guild.id}] サーバー脱退時のブースト削除に失敗しました: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """ブーストしたユーザー自身がサーバーを抜けた際にブーストを解除する"""
        try:
            booster_id = await self.bot.db.get_guild_booster(member.guild.id)
            if booster_id == str(member.id):
                await self.bot.db.deactivate_guild_boost(member.guild.id, member.id)
                logger.info(f"[{member.guild.id}] ブースター({member.id})が脱退したため、ブーストを解除しました。")
        except Exception as e:
            logger.error(f"[{member.guild.id}] メンバー脱退時のブーストチェックに失敗しました: {e}")

    @commands.Cog.listener(name="on_voice_state_update")
    async def auto_join(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """設定に基づいてボイスチャンネルへ自動接続する"""
        if member.bot:
            return

        if before.channel == after.channel or after.channel is None:
            return

        try:
            is_boosted = await self.bot.db.is_guild_boosted(member.guild.id)
            if not is_boosted:
                logger.debug(f"[{member.guild.id}] プレミアム未加入のため、自動接続をスキップしました。")
                return

            settings = await self.bot.db.get_guild_settings(member.guild.id)
        except Exception as e:
            logger.error(f"[{member.guild.id}] 自動接続用の設定取得に失敗: {e}")
            return

        if not settings.auto_join:
            return

        bot_key = str(self.bot.user.id)
        if bot_key not in settings.auto_join_config:
            return

        config = settings.auto_join_config[bot_key]
        target_vc_id = config.get("voice")
        target_tc_id = config.get("text")

        if after.channel.id == target_vc_id:
            if member.guild.voice_client:
                return

            try:
                # 接続（優先）
                await after.channel.connect()

                # 変数に保存（優先）
                self.read_channels[member.guild.id] = target_tc_id

                logger.success(f"[{member.guild.id}] 自動接続成功: {after.channel.name}")

                # 辞書をロード（バックグラウンド）
                asyncio.create_task(self.bot.db.load_guild_dict(member.guild.id))

                # DBへの保存（バックグラウンド）
                asyncio.create_task(
                    self.bot.db.save_voice_session(
                        guild_id=member.guild.id,
                        voice_channel_id=after.channel.id,
                        text_channel_id=target_tc_id,
                        bot_id=self.bot.user.id
                    )
                )

                # 通知メッセージ
                tc = member.guild.get_channel(target_tc_id)
                if tc:
                    embed = discord.Embed(
                        title="✅ 自動接続しました",
                        description=f"**{after.channel.name}** への入室を検知したため、自動接続しました。",
                        color=discord.Color.green()
                    )
                    await tc.send(embed=embed)
            except Exception as e:
                logger.error(f"[{member.guild.id}] 自動接続に失敗しました: {e}")

    @commands.Cog.listener(name="on_voice_state_update")
    async def auto_leave(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """VCにBot以外がいなくなった場合に自動で切断する"""
        if before.channel is None or before.channel == after.channel:
            return

        voice_client = member.guild.voice_client
        if not voice_client:
            return

        target_channel = voice_client.channel

        if before.channel.id != target_channel.id:
            return

        await asyncio.sleep(AUTO_LEAVE_INTERVAL)

        non_bot_members = [m for m in target_channel.members if not m.bot]

        if len(non_bot_members) == 0:
            guild_id = member.guild.id
            logger.info(f"[{guild_id}] VC({target_channel.name})にユーザーがいなくなったため自動切断します。")

            # 変数から削除（優先）
            self.read_channels.pop(guild_id, None)

            # 切断（優先）
            await voice_client.disconnect(force=True)

            # 辞書をアンロード（バックグラウンド）
            asyncio.create_task(self.bot.db.unload_guild_dict(guild_id))

            # DBからセッションを削除（バックグラウンド）
            asyncio.create_task(self._delete_session_background(guild_id))

    # ========================================
    # コマンド
    # ========================================

    @app_commands.command(name="join", description="ボイスチャンネルに接続し、このチャンネルを読み上げます")
    async def join(self, interaction: discord.Interaction):
        if not interaction.user.voice:
            embed = discord.Embed(
                title="❌ 接続エラー",
                description="ボイスチャンネルに接続してから実行してください。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        channel = interaction.user.voice.channel

        if interaction.guild.voice_client:
            embed = discord.Embed(
                title="⚠️ 既に接続しています",
                description=f"既に **{interaction.guild.voice_client.channel.name}** に接続しています。\n先に `/leave` で切断してください。",
                color=discord.Color.orange()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        other_bot = discord.utils.find(
            lambda m: m.bot and m.id != self.bot.user.id and ("Sumire" in m.name or "Vox" in m.name),
            channel.members
        )
        if other_bot:
            embed = discord.Embed(
                title="🚫 チャンネル重複",
                description=f"既に **{other_bot.display_name}** がこのチャンネルに参加しています。\n1つのチャンネルに複数のBotを入れることはできません。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            # 接続（優先）
            await channel.connect()

            # 変数に保存（優先）
            self.read_channels[interaction.guild.id] = interaction.channel.id

            # レスポンスを即座に返す（優先）
            embed = discord.Embed(
                title="✅ 接続しました",
                description=f"**{channel.name}** に接続しました。\nこのチャンネルのチャットを読み上げます。",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)

            logger.success(f"[{interaction.guild.id}] {channel.name} に接続しました。")

            # 辞書をロード（バックグラウンド）
            asyncio.create_task(self.bot.db.load_guild_dict(interaction.guild.id))

            # DBへの保存（バックグラウンド・遅延許容）
            asyncio.create_task(
                self.bot.db.save_voice_session(
                    guild_id=interaction.guild.id,
                    voice_channel_id=channel.id,
                    text_channel_id=interaction.channel.id,
                    bot_id=self.bot.user.id
                )
            )

        except discord.errors.ClientException as e:
            logger.error(f"[{interaction.guild.id}] VC接続エラー (ClientException): {e}")
            embed = discord.Embed(
                title="❌ 接続エラー",
                description="既にボイスチャンネルに接続しています。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except discord.errors.Forbidden as e:
            logger.error(f"[{interaction.guild.id}] VC接続エラー (権限不足): {e}")
            embed = discord.Embed(
                title="❌ 権限エラー",
                description=f"**{channel.name}** に接続する権限がありません。\nチャンネルの権限設定を確認してください。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except asyncio.TimeoutError:
            logger.error(f"[{interaction.guild.id}] VC接続エラー (タイムアウト)")
            embed = discord.Embed(
                title="❌ 接続タイムアウト",
                description="ボイスチャンネルへの接続がタイムアウトしました。\nしばらく時間をおいてから再度お試しください。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"[{interaction.guild.id}] VC接続中に予期しないエラーが発生しました: {e}")
            embed = discord.Embed(
                title="❌ 接続エラー",
                description="ボイスチャンネルへの接続中にエラーが発生しました。\nしばらく時間をおいてから再度お試しください。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="leave", description="切断して読み上げを終了します")
    async def leave(self, interaction: discord.Interaction):
        try:
            if interaction.guild.voice_client:
                guild_id = interaction.guild.id

                # 変数から削除（優先）
                self.read_channels.pop(guild_id, None)

                # 切断（優先）
                try:
                    await interaction.guild.voice_client.disconnect(force=True)

                    # レスポンスを即座に返す（優先）
                    embed = discord.Embed(
                        title="👋 切断しました",
                        description="ボイスチャンネルから切断しました。",
                        color=discord.Color.blue()
                    )
                    await interaction.response.send_message(embed=embed)

                    logger.info(f"[{guild_id}] VCから切断しました。")

                    # 辞書をアンロード（バックグラウンド）
                    asyncio.create_task(self.bot.db.unload_guild_dict(guild_id))

                    # DBからセッションを削除（バックグラウンド・遅延許容）
                    asyncio.create_task(self._delete_session_background(guild_id))

                except discord.errors.HTTPException as e:
                    logger.error(f"[{guild_id}] VC切断中にHTTPエラーが発生しました: {e}")
                    embed = discord.Embed(
                        title="❌ 切断エラー",
                        description="切断中に通信エラーが発生しました。\nBotは既に切断されている可能性があります。",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logger.error(f"[{guild_id}] VC切断中に予期しないエラーが発生しました: {e}")
                    embed = discord.Embed(
                        title="❌ 切断エラー",
                        description="切断中にエラーが発生しました。\nしばらく時間をおいてから再度お試しください。",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                embed = discord.Embed(
                    title="❌ 接続エラー",
                    description="Botはボイスチャンネルに接続していません。",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] leaveコマンド実行中に予期しないエラーが発生しました: {e}")
            try:
                embed = discord.Embed(
                    title="❌ エラー",
                    description="コマンド実行中にエラーが発生しました。",
                    color=discord.Color.red()
                )
                if interaction.response.is_done():
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    await interaction.response.send_message(embed=embed, ephemeral=True)
            except Exception as e2:
                logger.error(f"[{interaction.guild.id}] エラーが発生しました: {e2}")
                try:
                    await interaction.followup.send("エラーが発生しました。")
                except discord.HTTPException:
                    logger.error(f"[{interaction.guild.id}] エラーメッセージの送信にも失敗しました")

    @app_commands.command(name="set_voice", description="自分の声をカスタマイズします")
    @app_commands.choices(speaker=[
        app_commands.Choice(name="四国めたん (ノーマル)", value=2),
        app_commands.Choice(name="四国めたん (あまあま)", value=0),
        app_commands.Choice(name="四国めたん (ツンツン)", value=6),
        app_commands.Choice(name="四国めたん (セクシー)", value=4),
        app_commands.Choice(name="ずんだもん (ノーマル)", value=3),
        app_commands.Choice(name="ずんだもん (あまあま)", value=1),
        app_commands.Choice(name="ずんだもん (ツンツン)", value=7),
        app_commands.Choice(name="ずんだもん (セクシー)", value=5),
        app_commands.Choice(name="春日部つむぎ", value=8),
        app_commands.Choice(name="雨晴はう", value=10),
        app_commands.Choice(name="波音リツ", value=9),
        app_commands.Choice(name="玄野武宏 (ノーマル)", value=11),
        app_commands.Choice(name="玄野武宏 (喜び)", value=39),
        app_commands.Choice(name="玄野武宏 (ツンギレ)", value=40),
        app_commands.Choice(name="玄野武宏 (悲しみ)", value=41),
        app_commands.Choice(name="白上虎太郎 (ふつう)", value=12),
        app_commands.Choice(name="白上虎太郎 (わーい)", value=32),
        app_commands.Choice(name="白上虎太郎 (びくびく)", value=33),
        app_commands.Choice(name="白上虎太郎 (おこ)", value=34),
        app_commands.Choice(name="白上虎太郎 (びえーん)", value=35),
        app_commands.Choice(name="青山龍星", value=13),
        app_commands.Choice(name="冥鳴ひまり", value=14),
        app_commands.Choice(name="九州そら (ノーマル)", value=16),
        app_commands.Choice(name="九州そら (あまあま)", value=15),
    ])
    @app_commands.describe(
        speaker="話者を選択してください",
        speed="話速（0.5〜2.0）",
        pitch="音高（-0.15〜0.15）"
    )
    async def set_voice(
        self,
        interaction: discord.Interaction,
        speaker: app_commands.Choice[int],
        speed: float = 1.0,
        pitch: float = 0.0
    ):
        # 値の範囲チェック
        if not (0.5 <= speed <= 2.0):
            embed = discord.Embed(
                title="❌ 無効な値",
                description="話速は 0.5〜2.0 の範囲で指定してください。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if not (-0.15 <= pitch <= 0.15):
            embed = discord.Embed(
                title="❌ 無効な値",
                description="音高は -0.15〜0.15 の範囲で指定してください。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            await self.bot.db.set_user_setting(
                interaction.user.id,
                speaker.value,
                speed,
                pitch
            )

            embed = discord.Embed(
                title="✅ 声を設定しました",
                description=f"**話者**: {speaker.name}\n**話速**: {speed}\n**音高**: {pitch}",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 声の設定に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ エラー",
                description="声の設定中にエラーが発生しました。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

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
    async def dictionary(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        word: str = None,
        reading: str = None
    ):
        words_dict = await self._get_guild_dict(interaction)
        if words_dict is None:
            return

        if action.value == "list":
            if not words_dict:
                embed = discord.Embed(
                    title="📖 辞書一覧",
                    description="登録されている単語はありません。",
                    color=discord.Color.blue()
                )
                return await interaction.response.send_message(embed=embed)

            embed = create_dictionary_embed(words_dict, page=0)
            view = DictionaryView(words_dict) if len(words_dict) > 10 else None
            await interaction.response.send_message(embed=embed, view=view)

        elif action.value == "add":
            if not word or not reading:
                embed = discord.Embed(
                    title="❌ 入力エラー",
                    description="単語と読み方を両方指定してください。",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            if not is_katakana(reading):
                embed = discord.Embed(
                    title="❌ 入力エラー",
                    description="読み方はカタカナで入力してください。",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            words_dict[word] = reading

            try:
                await self.bot.db.add_or_update_dict(interaction.guild.id, words_dict)
                embed = discord.Embed(
                    title="✅ 辞書に追加しました",
                    description=f"**{word}** → **{reading}**",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            except Exception as e:
                logger.error(f"[{interaction.guild.id}] 辞書の追加に失敗しました: {e}")
                embed = discord.Embed(
                    title="❌ エラー",
                    description="辞書の追加中にエラーが発生しました。",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)

        elif action.value == "delete":
            if not word:
                embed = discord.Embed(
                    title="❌ 入力エラー",
                    description="削除する単語を指定してください。",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            if word not in words_dict:
                embed = discord.Embed(
                    title="❌ 見つかりません",
                    description=f"**{word}** は辞書に登録されていません。",
                    color=discord.Color.red()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

            del words_dict[word]

            try:
                await self.bot.db.add_or_update_dict(interaction.guild.id, words_dict)
                embed = discord.Embed(
                    title="✅ 辞書から削除しました",
                    description=f"**{word}** を削除しました。",
                    color=discord.Color.green()
                )
                await interaction.response.send_message(embed=embed)
            except Exception as e:
                logger.error(f"[{interaction.guild.id}] 辞書の削除に失敗しました: {e}")
                embed = discord.Embed(
                    title="❌ エラー",
                    description="辞書の削除中にエラーが発生しました。",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot):
    await bot.add_cog(Voice(bot))
