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
from src.utils.views import ConfigSearchView, DictionaryView
import uuid
from dataclasses import dataclass, field

AUTO_LEAVE_INTERVAL: int = 1
DISCONNECT_CONFIRM_DELAY: int = 30


def is_katakana(text: str) -> bool:
    """全角カタカナ、長音記号のみで構成されているか判定"""
    return re.fullmatch(r'^[ァ-ヶーヴ]+$', text) is not None


def format_rows(rows):
    if not rows: return "登録なし"
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
        self.queues: dict[int, asyncio.Queue[AudioTask]] = {}  # AudioTaskのキュー
        self.is_processing = {}
        self.read_channels = {}

        load_dotenv()
        self.GLOBAL_DICT_ID = int(os.getenv("GLOBAL_DICT_ID"))

        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
            logger.info(f"一時ディレクトリを作成しました: {self.temp_dir}")

    def get_queue(self, guild_id: int) -> asyncio.Queue[AudioTask]:
        if guild_id not in self.queues:
            self.queues[guild_id] = asyncio.Queue()
            self.is_processing[guild_id] = False
        return self.queues[guild_id]

    async def apply_dictionary(self, content: str, guild_id: int) -> str:
        """辞書を適用してテキストを変換する"""
        # guild_id が 0 の場合はスキップ
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

    async def _generate_audio(self, audio_task: AudioTask, guild_id: int):
        """音声ファイルを生成する（バックグラウンドタスク）"""
        try:
            # DBからユーザー設定を読み込む
            try:
                s = await self.bot.db.get_user_setting(audio_task.author_id)
            except Exception as e:
                logger.error(f"[{guild_id}] ユーザー設定の取得に失敗しました (user_id: {audio_task.author_id}): {e}")
                s = {"speaker": 1, "speed": 1.0, "pitch": 0.0}

            is_boosted = self.bot.db.is_guild_boosted(guild_id)
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
                # 自動接続設定があれば再接続を試みるロジック（簡易版）
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
            # VoiceClientの状態が異常な場合、リセットを検討
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
                await asyncio.sleep(0.5)  # ファイルハンドルが確実に閉じられるまで待機
                os.remove(audio_task.file_path)
                logger.debug(f"[{guild_id}] 一時ファイルを削除しました: {audio_task.file_path}")
        except Exception as e:
            logger.warning(f"[{guild_id}] 一時ファイルの削除に失敗しました: {e}")

    @commands.Cog.listener(name="on_voice_state_update")
    async def on_vc_notification(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """ユーザーの入退出を検知して読み上げる"""
        try:
            # Bot自身や、BotがVCに参加していない場合は無視
            if member.bot or not member.guild.voice_client:
                return

            bot_vc = member.guild.voice_client.channel

            try:
                settings = await self.bot.db.get_guild_settings(member.guild.id)
            except Exception as e:
                logger.error(f"[{member.guild.id}] サーバー設定の取得に失敗しました: {e}")
                return

            # 設定が無効なら終了
            if not settings.read_vc_status:
                return

            content = None
            # 入室: 以前のチャンネルがBotのVCではなく、現在のチャンネルがBotのVCである場合
            if before.channel != bot_vc and after.channel == bot_vc:
                suffix = "さん" if settings.add_suffix else ""
                content = f"{member.display_name}{suffix}が入室しました"
            # 退出: 以前のチャンネルがBotのVCで、現在のチャンネルがBotのVCではなくなった場合
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
            f"[DEBUG] on_message received in {message.guild.name} from {message.author.display_name}: {message.content[:50]}")

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
            logger.debug(f"[DEBUG] Instance is NOT active for guild {message.guild.id}. Skipping message.")
            return

        settings = await self.bot.db.get_guild_settings(message.guild.id)
        is_boosted = await self.bot.db.is_guild_boosted(message.guild.id)

        # ブーストされている場合は制限を緩和
        # 無料: 50文字固定, 1ブースト以上: 設定値（最大200文字）
        if is_boosted:
            max_chars = min(settings.max_chars, 200)
        else:
            max_chars = 50

        logger.debug(f"[DEBUG] Processing message. is_boosted={is_boosted}, max_chars={max_chars}")

        content = message.clean_content

        # Discordのタイムスタンプ表現 <t:UNIX:FORMAT> を読み上げ用に変換
        # 例:
        #   <t:1700000000:R> -> 「3分前」
        #   <t:1700000000:F> -> 「2026年2月11日23時23分」
        #   <t:1700000000:S> -> 「2026年2月11日23時23分33秒」（非標準/環境依存のため独自対応）
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

            # ローカル時刻で読み上げ（自然なため）
            local_dt = dt.astimezone()

            if fmt == "t":  # 16:20
                return f"{local_dt.hour}時{local_dt.minute}分"
            if fmt == "T":  # 16:20:30
                return f"{local_dt.hour}時{local_dt.minute}分{local_dt.second}秒"
            if fmt == "d":  # 日付のみ
                return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日"
            if fmt == "D":  # 日付のみ（表記違いだが読み上げは同じに寄せる）
                return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日"
            if fmt == "f":  # 日付+時分
                return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日{local_dt.hour}時{local_dt.minute}分"
            if fmt == "F":  # 日付+時分（曜日は省略して読み上げを簡潔に）
                return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日{local_dt.hour}時{local_dt.minute}分"

            # 独自: :S を「日付+時分秒」として読む（ユーザー要望対応）
            if fmt == "S":
                return (
                    f"{local_dt.year}年{local_dt.month}月{local_dt.day}日"
                    f"{local_dt.hour}時{local_dt.minute}分{local_dt.second}秒"
                )

            # 不明フォーマットはデフォルト扱い
            return f"{local_dt.year}年{local_dt.month}月{local_dt.day}日{local_dt.hour}時{local_dt.minute}分"

        # <t:1234567890:R> / <t:1234567890> どちらも対応
        # :S も含め、1文字フォーマットは幅広く拾う（tTdDfFR + S）
        content = re.sub(
            r"<t:(?P<unix>\d+)(?::(?P<fmt>[A-Za-z]))?>",
            _format_discord_timestamp_for_tts,
            content
        )

        # Discordクライアント側で既に「2026/02/11 23:23:33」のような文字列に展開される環境向け
        # それ自体を日本語の読み上げに変換する（スラッシュ/コロン読み上げ事故対策）
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

        # グローバル辞書（ID が 0 でない場合のみ適用）
        if self.GLOBAL_DICT_ID and self.GLOBAL_DICT_ID != 0:
            content = await self.apply_dictionary(content, self.GLOBAL_DICT_ID)

        # ローマ字を仮名読みに変換
        if settings.read_romaji:
            content = romkan2.to_hiragana(content)

        # 長文対策
        if len(content) > max_chars:
            content = content[:max_chars] + "、以下略"

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

            self.read_channels.pop(guild_id, None)

            # 辞書をアンロード
            self.bot.db.unload_guild_dict(guild_id)

            await _cleanup_queue(guild_id)

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
            # そのサーバーのブースターが抜けたユーザーか確認
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

        # 誰かがチャンネルに参加したときのみ判定
        if before.channel == after.channel or after.channel is None:
            return

        try:
            # プレミアムチェック (ブーストされていない場合は自動接続をスキップ)
            is_boosted = await self.bot.db.is_guild_boosted(member.guild.id)
            if not is_boosted:
                logger.debug(f"[{member.guild.id}] プレミアム未加入のため、自動接続をスキップしました。")
                return

            settings = await self.bot.db.get_guild_settings(member.guild.id)
        except Exception as e:
            logger.error(f"[{member.guild.id}] 自動接続用の設定取得に失敗: {e}")
            return

        # 全体設定が無効なら何もしない
        if not settings.auto_join:
            return

        # このBot用の設定があるか確認
        bot_key = str(self.bot.user.id)
        if bot_key not in settings.auto_join_config:
            return

        config = settings.auto_join_config[bot_key]
        target_vc_id = config.get("voice")
        target_tc_id = config.get("text")

        # 参加したチャンネルが指定の監視VCであるか確認
        if after.channel.id == target_vc_id:
            # すでにどこかのVCに接続している場合はスキップ
            if member.guild.voice_client:
                return

            try:
                await after.channel.connect()
                self.read_channels[member.guild.id] = target_tc_id

                # 辞書をロード
                await self.bot.db.load_guild_dict(member.guild.id)

                logger.success(f"[{member.guild.id}] 自動接続成功: {after.channel.name}")

                # 通知メッセージ（任意）
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

        # Bot自身が接続しているギルドの音声クライアントを取得
        voice_client = member.guild.voice_client
        if not voice_client:
            return

        target_channel = voice_client.channel

        if before.channel.id != target_channel.id:
            return

        await asyncio.sleep(AUTO_LEAVE_INTERVAL)

        # Bot以外のメンバー（Bot: False）のリストを取得
        non_bot_members = [m for m in target_channel.members if not m.bot]

        # Bot以外がいなければ切断
        if len(non_bot_members) == 0:
            logger.info(f"[{member.guild.id}] VC({target_channel.name})にユーザーがいなくなったため自動切断します。")

            self.read_channels.pop(member.guild.id, None)

            # 辞書をアンロード
            self.bot.db.unload_guild_dict(member.guild.id)

            await voice_client.disconnect(force=True)

    @app_commands.command(name="join", description="ボイスチャンネルに接続し、このチャンネルを読み上げます")
    async def join(self, interaction: discord.Interaction):
        # ユーザーがボイスチャンネルに接続しているか確認
        if not interaction.user.voice:
            embed = discord.Embed(
                title="❌ 接続エラー",
                description="ボイスチャンネルに接続してから実行してください。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        channel = interaction.user.voice.channel

        # 既に自分が接続しているか確認
        if interaction.guild.voice_client:
            embed = discord.Embed(
                title="⚠️ 既に接続しています",
                description=f"既に **{interaction.guild.voice_client.channel.name}** に接続しています。\n先に `/leave` で切断してください。",
                color=discord.Color.orange()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 重複チェック: 同じチャンネルに他のBot（SumireVoxシリーズ）がいないか
        # 自分のBot名に "SumireVox" が含まれている前提で、同じプレフィックスのBotを探す
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
            await channel.connect()
            self.read_channels[interaction.guild.id] = interaction.channel.id

            # 辞書をロード
            await self.bot.db.load_guild_dict(interaction.guild.id)

            logger.success(f"[{interaction.guild.id}] {channel.name} に接続しました。")

            embed = discord.Embed(
                title="✅ 接続しました",
                description=f"**{channel.name}** に接続しました。\nこのチャンネルのチャットを読み上げます。",
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed)

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
                self.read_channels.pop(interaction.guild.id, None)

                # 辞書をアンロード
                self.bot.db.unload_guild_dict(interaction.guild.id)

                try:
                    await interaction.guild.voice_client.disconnect(force=True)
                    logger.info(f"[{interaction.guild.id}] VCから切断しました。")
                    embed = discord.Embed(
                        title="👋 切断しました",
                        description="ボイスチャンネルから切断しました。",
                        color=discord.Color.blue()
                    )
                    await interaction.response.send_message(embed=embed)
                except discord.errors.HTTPException as e:
                    logger.error(f"[{interaction.guild.id}] VC切断中にHTTPエラーが発生しました: {e}")
                    embed = discord.Embed(
                        title="❌ 切断エラー",
                        description="切断中に通信エラーが発生しました。\nBotは既に切断されている可能性があります。",
                        color=discord.Color.red()
                    )
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                except Exception as e:
                    logger.error(f"[{interaction.guild.id}] VC切断中に予期しないエラーが発生しました: {e}")
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
            except Exception as e:
                logger.error(f"[{interaction.guild.id}] エラーが発生しました: {e}")
                try:
                    await interaction.followup.send("エラーが発生しました。")
                except discord.HTTPException:
                    logger.error(f"[{interaction.guild.id}] エラーメッセージの送信にも失敗しました")

    @app_commands.command(name="set_voice", description="自分の声をカスタマイズします")
    @app_commands.choices(speaker=[
        app_commands.Choice(name="四国めたん (ノーマル)", value=2),
        app_commands.Choice(name="四_国めたん (あまあま)", value=0),
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
    @app_commands.rename(speaker="キャラクター", speed="スピード", pitch="ピッチ")
    @app_commands.describe(
        speaker="自分の声のキャラクターを変更できます",
        speed="自分の声のスピードを変更できます (デフォルトは1.0)",
        pitch="自分の声のピッチを変更できます (デフォルトは0.0)"
    )
    async def set_voice(self, interaction: discord.Interaction, speaker: int, speed: float = 1.0, pitch: float = 0.0):
        # ブーストチェック
        is_boosted = await self.bot.db.is_guild_boosted(interaction.guild.id)

        # 無料版制限: 速度・ピッチはデフォルト以外不可
        if not is_boosted:
            if speed != 1.0 or pitch != 0.0:
                embed = discord.Embed(
                    title="💎 プレミアム機能",
                    description="読み上げ速度とピッチの変更は**プレミアムプラン（1ブースト以上）**限定機能です。\n"
                                "現在はキャラクターの変更のみご利用いただけます。",
                    color=discord.Color.gold()
                )
                return await interaction.response.send_message(embed=embed, ephemeral=True)

        # バリデーション
        speed = max(0.5, min(2.0, speed))
        pitch = max(-0.15, min(0.15, pitch))

        # DBに保存
        try:
            await self.bot.db.set_user_setting(interaction.user.id, speaker, speed, pitch)
        except Exception as e:
            logger.error(f"音声設定の保存に失敗しました (user_id: {interaction.user.id}): {e}")
            embed = discord.Embed(
                title="❌ 保存エラー",
                description="音声設定の保存中にエラーが発生しました。\nしばらく時間をおいてから再度お試しください。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        embed = discord.Embed(
            title="✅ 音声設定を保存しました",
            description=f"{interaction.user.display_name}さんの音声設定を更新しました。",
            color=discord.Color.green()
        )
        embed.add_field(name="速度", value=f"`{speed}`", inline=True)
        embed.add_field(name="ピッチ", value=f"`{pitch}`", inline=True)

        return await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dictionary", description="辞書を管理します（表示・追加・削除）")
    async def dictionary(self, interaction: discord.Interaction):
        try:
            guild_rows = await self._get_guild_dict(interaction)
            if guild_rows is None: return

            embed = self.create_dictionary_embed(guild_rows)

            view = DictionaryView(self.bot.db, self.bot)
            await interaction.response.send_message(embed=embed, view=view)
            view.message = await interaction.original_response()
        except Exception as e:
            logger.error(f"辞書管理画面の表示に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ 辞書の表示エラー",
                description="辞書管理画面の表示中にエラーが発生しました。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    def create_dictionary_embed(self, guild_rows):
        """辞書表示用Embedを生成する"""
        embed = discord.Embed(title="📖 辞書管理", color=discord.Color.blue(), description=format_rows(guild_rows))
        embed.set_footer(text="下のボタンから単語を追加・削除できます")
        return embed

    @app_commands.command(name="config", description="サーバーごとの読み上げ設定を変更します")
    async def config(self, interaction: discord.Interaction):
        # サーバー管理権限またはBotの作成者かチェック
        is_admin = interaction.user.guild_permissions.manage_guild
        is_owner = await self.bot.is_owner(interaction.user)

        if not (is_admin or is_owner):
            embed = discord.Embed(
                title="❌ 権限エラー",
                description="このコマンドを実行するには、「サーバー管理」権限が必要です。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            return

        try:
            settings = await self.bot.db.get_guild_settings(interaction.guild.id)
            is_boosted = await self.bot.db.is_guild_boosted(interaction.guild.id)
            embed = self.create_config_embed(interaction.guild, settings, is_boosted)
            view = ConfigSearchView(self.bot.db, self.bot)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=False)
            view.message = await interaction.original_response()
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 設定画面の表示に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ 設定画面の表示エラー",
                description="設定画面の表示中にエラーが発生しました。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

    def create_config_embed(self, guild, settings, is_boosted=False):
        """設定用Embedを生成する共通メソッド"""
        embed = discord.Embed(
            title="⚙️ サーバー設定",
            description=f"現在の設定値は以下の通りです。変更するには下のメニューから項目を選択してください。\n"
                        f"※**{self.bot.user.name}** インスタンスの設定を表示しています。",
            color=discord.Color.blue()
        )

        # 基本設定
        # 無料: 50文字固定, 1ブースト以上: 設定値（最大200文字）
        if is_boosted:
            effective_limit = min(settings.max_chars, 200)
            char_limit_text = f"📝 `{effective_limit}` 文字 (設定: {settings.max_chars})"
        else:
            char_limit_text = "📝 `50` 文字 (無料版制限)"

        embed.add_field(name="文字数制限", value=char_limit_text, inline=True)
        embed.add_field(name="さん付け", value="✅ 有効" if settings.add_suffix else "❌ 無効", inline=True)
        embed.add_field(name="ローマ字読み", value="✅ 有効" if settings.read_romaji else "❌ 無効", inline=True)

        embed.add_field(name="メンション", value="✅ 有効" if settings.read_mention else "❌ 無効", inline=True)
        embed.add_field(name="添付ファイル", value="✅ 有効" if settings.read_attachments else "❌ 無効", inline=True)
        embed.add_field(name="入退出通知", value="✅ 有効" if settings.read_vc_status else "❌ 無効", inline=True)

        embed.add_field(name="絵文字の読み上げ", value="✅ 有効" if settings.read_emoji else "❌ 無効", inline=True)
        embed.add_field(name="コードブロックの省略", value="✅ 有効" if settings.skip_code_blocks else "❌ 無効",
                        inline=True)
        embed.add_field(name="URLの省略", value="✅ 有効" if settings.skip_urls else "❌ 無効", inline=True)

        # 自動接続設定
        bot_key = str(self.bot.user.id)
        auto_join_status = "ー"
        if settings.auto_join and bot_key in settings.auto_join_config:
            conf = settings.auto_join_config[bot_key]
            vc = guild.get_channel(conf["voice"])
            tc = guild.get_channel(conf["text"])
            if vc and tc:
                auto_join_status = f"✅ **有効**\n└ 監視: {vc.mention}\n└ 出力: {tc.mention}"
            else:
                auto_join_status = "⚠️ 設定不備"

        embed.add_field(name="🤖 このBotの自動接続設定", value=auto_join_status, inline=False)
        return embed


async def setup(bot):
    await bot.add_cog(Voice(bot))
