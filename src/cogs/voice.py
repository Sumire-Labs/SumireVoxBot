import discord
from discord import app_commands
from discord.ext import commands
import os
import asyncio
import re
import jaconv
from loguru import logger
import romkan2

GLOBAL_DICT_ID = 1460650319028687045


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
            logger.info(f"一時ディレクトリを作成しました: {self.temp_dir}")

    def get_queue(self, guild_id: int) -> asyncio.Queue:
        if guild_id not in self.queues:
            self.queues[guild_id] = asyncio.Queue()
            self.is_processing[guild_id] = False
        return self.queues[guild_id]

    async def apply_dictionary(self, content: str, guild_id: int) -> str:
        """辞書を適用してテキストを変換する"""
        words = await self.bot.db.get_dict(guild_id)
        if words and isinstance(words, dict):
            for word in sorted(words.keys(), key=len, reverse=True):
                pattern = re.compile(re.escape(word), re.IGNORECASE)
                content = pattern.sub(words[word], content)
        return content

    @logger.catch()
    async def play_next(self, guild_id: int):
        self.is_processing[guild_id] = True
        queue = self.get_queue(guild_id)
        guild = self.bot.get_guild(guild_id) or await self.bot.fetch_guild(guild_id)

        try:
            while not queue.empty():
                text, author_id = await queue.get()

                # DBからユーザー設定を読み込む
                s = await self.bot.db.get_user_setting(author_id)

                file_path = f"{self.temp_dir}/audio_{guild_id}.wav"
                try:
                    # kana, digit, ascii すべてを全角(h2z)にし、英字は小文字(lower)にする
                    normalized_text = jaconv.h2z(text, kana=True, digit=True, ascii=True).lower()

                    logger.debug(f"[{guild_id}] 音声生成開始: {normalized_text[:20]}...")

                    await self.bot.vv_client.generate_sound(
                        text=normalized_text,
                        speaker_id=s["speaker"],
                        speed=s["speed"],
                        pitch=s["pitch"],
                        output_path=file_path
                    )

                    if guild.voice_client:
                        source = discord.FFmpegPCMAudio(
                            file_path,
                            options="-vn -loglevel quiet",
                            before_options="-loglevel quiet",
                        )
                        stop_event = asyncio.Event()
                        guild.voice_client.play(
                            source,
                            after=lambda e: self.bot.loop.call_soon_threadsafe(stop_event.set)
                        )
                        await stop_event.wait()
                        logger.info(f"[{guild_id}] 再生完了: {normalized_text[:15]}")
                except Exception as e:
                    logger.error(f"[{guild_id}] 再生中にエラーが発生しました: {e}")
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
        if message.content.startswith(("!", "！")):
            return

        settings = await self.bot.db.get_guild_settings(message.guild.id)
        content = message.clean_content

        # 辞書適応
        content = await self.apply_dictionary(content, message.guild.id)
        content = await self.apply_dictionary(content, GLOBAL_DICT_ID)

        # コードブロックを省略
        content = re.sub(r"```.*?```", "、コードブロック省略、", content, flags=re.DOTALL)

        # URLを省略
        content = re.sub(r'https?://[\w/:%#$&?()~.=+\-]+', '、URL省略、', content)

        # ローマ字を仮名読みに変換
        if settings.read_romaji:
            content = romkan2.to_hiragana(content)

        # 長文対策
        settings = await self.bot.db.get_guild_settings(message.guild.id)
        limit: int = 50
        if settings.max_chars:
            limit = settings.max_chars
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
            logger.warning(f"[{guild_id}] VC切断を検知したため、キューをクリアしました。")

    @app_commands.command(name="join", description="ボイスチャンネルに接続し、このチャンネルを読み上げます")
    async def join(self, interaction: discord.Interaction):
        if interaction.user.voice:
            # 読み上げチャンネルを記憶
            self.read_channels[interaction.guild.id] = interaction.channel.id

            channel = interaction.user.voice.channel
            await channel.connect()
            logger.success(f"[{interaction.guild.id}] {channel.name} に接続しました。")
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
            logger.info(f"[{interaction.guild.id}] VCから切断しました。")
            await interaction.response.send_message("👋 切断しました。")
        else:
            await interaction.response.send_message("❌ Botはボイスチャンネルに接続していません。", ephemeral=True)

    @app_commands.command(name="set_voice", description="自分の声をカスタマイズします")
    @app_commands.choices(speaker=[
        app_commands.Choice(name="四国めたん (あまあま)", value=0),
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
        app_commands.Choice(name="後鬼", value=27),
        app_commands.Choice(name="No.7", value=29),
        app_commands.Choice(name="ちび式じい", value=42),
        app_commands.Choice(name="櫻歌ミコ", value=43),
        app_commands.Choice(name="小夜/SAYO", value=46),
        app_commands.Choice(name="ナースロボ＿タイプＴ", value=47),
        app_commands.Choice(name="聖騎士紅桜", value=50),
        app_commands.Choice(name="雀松朱司", value=52),
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

    @app_commands.command(name="add_word", description="単語を辞書に登録します")
    @app_commands.describe(word="登録する単語", reading="読み方（カタカナのみ）")
    async def add_word(self, interaction: discord.Interaction, word: str, reading: str):
        # スペース削除と変換
        word = word.strip()
        reading = reading.strip()

        try:
            normalized_reading = jaconv.h2z(reading, kana=True, digit=False, ascii=False)
            normalized_reading = jaconv.hira2kata(normalized_reading)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 読み方の正規化に失敗しました: {e}")
            return await interaction.response.send_message(
                "❌ 読み方の変換中にエラーが発生しました。",
                ephemeral=True
            )

        # 最終チェック
        if not is_katakana(normalized_reading):
            return await interaction.response.send_message(
                "❌ 読み方は「ひらがな」または「カタカナ」で入力してください。",
                ephemeral=True
            )

        if not word:
            return await interaction.response.send_message("❌ 単語を入力してください。", ephemeral=True)

        try:
            # 既存の辞書を取得
            words_dict = await self.bot.db.get_dict(interaction.guild.id)

            # 辞書が存在しない場合は新規作成
            if not words_dict or not isinstance(words_dict, dict):
                words_dict = {}

            # 新しい単語と読みを追加
            words_dict[word] = normalized_reading

            # 更新された辞書をDBに保存
            await self.bot.db.add_or_update_dict(interaction.guild.id, words_dict)

            logger.success(f"[{interaction.guild.id}] 辞書登録: {word} -> {normalized_reading}")
            return await interaction.response.send_message(
                f"🏠 サーバー辞書に登録しました: `{word}` → `{normalized_reading}`")
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書登録に失敗しました: {e}")
            return await interaction.response.send_message(
                "❌ 辞書への登録中にエラーが発生しました。",
                ephemeral=True
            )

    @app_commands.command(name="remove_word", description="辞書から単語を削除します")
    @app_commands.describe(word="削除する単語")
    async def remove_word(self, interaction: discord.Interaction, word: str):
        word = word.strip()
        # DBから現在の辞書を取得
        try:
            words_dict = await self.bot.db.get_dict(interaction.guild.id)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書の取得に失敗しました: {e}")
            return await interaction.response.send_message("❌ 辞書の取得中にエラーが発生しました。", ephemeral=True)

        # 辞書が存在しない、または空の場合
        if not words_dict or not isinstance(words_dict, dict):
            return await interaction.response.send_message(f"⚠️ `{word}` は辞書に登録されていません。", ephemeral=True)

        # 削除する単語が辞書に存在するかチェック
        if word not in words_dict:
            return await interaction.response.send_message(f"⚠️ `{word}` は辞書に登録されていません。", ephemeral=True)

        # 辞書から単語を削除
        try:
            del words_dict[word]
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書からの単語削除に失敗しました: {e}")
            return await interaction.response.send_message("❌ 辞書の更新中にエラーが発生しました。", ephemeral=True)

        # 更新された辞書をDBに保存
        try:
            success = await self.bot.db.add_or_update_dict(interaction.guild.id, words_dict)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書の保存に失敗しました: {e}")
            return await interaction.response.send_message("❌ 辞書の保存中にエラーが発生しました。", ephemeral=True)

        if success:
            logger.success(f"[{interaction.guild.id}] 辞書削除: {word}")
            return await interaction.response.send_message(f"🗑️ `{word}` を辞書から削除しました。")
        else:
            logger.warning(f"[{interaction.guild.id}] 辞書削除に失敗しました: {word}")
            return await interaction.response.send_message(f"⚠️ 削除に失敗しました。", ephemeral=True)

    @app_commands.command(name="dictionary", description="辞書に登録されている単語一覧を表示します")
    async def dictionary(self, interaction: discord.Interaction):
        try:
            guild_rows = await self.bot.db.get_dict(interaction.guild.id)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書の取得に失敗しました: {e}")
            return await interaction.response.send_message("❌ 辞書の取得中にエラーが発生しました。", ephemeral=True)

        try:
            embed = discord.Embed(title="📖 辞書一覧", color=discord.Color.blue())
            embed.add_field(name="🏠 サーバー辞書", value=format_rows(guild_rows), inline=False)

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"辞書一覧の送信に失敗しました: {e}")
            await interaction.response.send_message("❌ 辞書一覧の表示中にエラーが発生しました。", ephemeral=True)

    @app_commands.command(name="config", description="サーバーごとの読み上げ設定を変更します")
    @app_commands.describe(
        item="設定する項目を選んでください",
        value="ONならTrue、OFFならFalse、または数値を入力してください"
    )
    @app_commands.choices(item=[
        app_commands.Choice(name="自動接続 (True/False)", value="auto_join"),
        app_commands.Choice(name="文字数制限 (10-500)", value="max_chars"),
        app_commands.Choice(name="入退出の読み上げ (True/False)", value="read_vc_status"),
        app_commands.Choice(name="メンション読み上げ (True/False)", value="read_mention"),
        app_commands.Choice(name="さん付け (True/False)", value="add_suffix"),
        app_commands.Choice(name="ローマ字読み (True/False)", value="read_romaji")
    ])
    async def config(self, interaction: discord.Interaction, item: str, value: str):
        # 1. 現在の設定を取得（なければデフォルト値が返る）
        settings = await self.bot.db.get_guild_settings(interaction.guild.id)

        logger.debug(f"サーバー設定の更新を行います...現在の設定: {settings}")

        try:
            # 現在の値を取得（表示用）
            old_value = getattr(settings, item)

            # 2. 値の型変換
            if isinstance(old_value, bool):
                # bool型の場合の変換
                new_value = value.lower() in ("true", "yes", "on", "1", "有効", "きおん")
            elif isinstance(old_value, int):
                # int型の場合の変換
                if not value.isdigit():
                    return await interaction.response.send_message("❌ 数値を入力してください。", ephemeral=True)
                new_value = int(value)
            else:
                new_value = value

            # 3. 値の反映とバリデーション
            # Pydanticモデルを更新（ここで ge=10 などの制約がチェックされる）
            setattr(settings, item, new_value)

            # 4. データベースへ保存（UPSERTなので新規でも更新でもOK）
            await self.bot.db.set_guild_settings(interaction.guild.id, settings)

            await interaction.response.send_message(
                f"✅ 設定を更新しました：**{item}**\n"
                f"値：`{old_value}` ➡ **`{new_value}`**"
            )

        except Exception as e:
            # Pydanticのバリデーションエラーなどのハンドリング
            logger.error(f"Config update failed: {e}")
            await interaction.response.send_message(
                f"❌ 設定の更新に失敗しました。正しい値を入力してください。\n(エラー内容: {e})",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Voice(bot))
