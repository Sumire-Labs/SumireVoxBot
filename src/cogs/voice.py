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
from src.utils.views import ConfigSearchView


AUTO_LEAVE_INTERVAL: int = 1


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

        load_dotenv()
        self.GLOBAL_DICT_ID = int(os.getenv("GLOBAL_DICT_ID"))

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
                try:
                    await self._process_and_play(guild, text, author_id)
                except Exception as e:
                    logger.error(f"[{guild_id}] 再生中にエラーが発生しました: {e}")
                finally:
                    queue.task_done()
        finally:
            self.is_processing[guild_id] = False

    async def _process_and_play(self, guild, text, author_id):
        """1つのテキストを処理して再生する内部メソッド"""
        # DBからユーザー設定を読み込む
        s = await self.bot.db.get_user_setting(author_id)
        file_path = f"{self.temp_dir}/audio_{guild.id}.wav"

        # 正規化処理
        normalized_text = jaconv.h2z(text, kana=True, digit=True, ascii=True).lower()
        logger.debug(f"[{guild.id}] 音声生成開始: {normalized_text[:20]}...")

        # 音声生成
        await self.bot.vv_client.generate_sound(
            text=normalized_text,
            speaker_id=s["speaker"],
            speed=s["speed"],
            pitch=s["pitch"],
            output_path=file_path
        )

        # ボイスチャットに接続していない場合はスキップ
        if not guild.voice_client:
            return

        # 再生処理
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
        logger.info(f"[{guild.id}] 再生完了: {normalized_text[:15]}")

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
                    queue = self.get_queue(member.guild.id)
                    # ユーザーのデフォルト設定（speakerなど）を使用するためmember.idを渡す
                    await queue.put((content, member.id))

                    if not self.is_processing[member.guild.id]:
                        asyncio.create_task(self.play_next(member.guild.id))
                except Exception as e:
                    logger.error(f"[{member.guild.id}] VC通知のキューイングに失敗しました: {e}")
        except Exception as e:
            logger.error(f"[{member.guild.id}] VC通知処理中にエラーが発生しました: {e}")

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

        # メンション読み上げ
        if settings.read_mention:
            for mention in message.mentions:
                content = content.replace(f"@{mention.display_name}", f"メンション{mention.display_name}")

        # コードブロックを省略
        if settings.skip_code_blocks:
            content = re.sub(r"```.*?```", "、コードブロック省略、", content, flags=re.DOTALL)

        # URLを省略
        if settings.skip_urls:
            content = re.sub(r'https?://[\w/:%#$&?()~.=+\-]+', '、URL省略、', content)

        # サーバー絵文字の処理
        content = re.sub(r'<a?:(\w+):?\d+>', r'\1', content)

        # 絵文字の読み上げ
        if settings.read_emoji:
            content = emoji.demojize(content, language='ja')
            content = content.replace(":", "、")
        else:
            content = emoji.replace_emoji(content, "")

        # 辞書適応
        content = await self.apply_dictionary(content, message.guild.id)
        content = await self.apply_dictionary(content, self.GLOBAL_DICT_ID)

        # ローマ字を仮名読みに変換
        if settings.read_romaji:
            content = romkan2.to_hiragana(content)

        # 長文対策
        limit: int = 50
        if settings.max_chars:
            limit = settings.max_chars
        if len(content) > limit:
            content = content[:limit] + "、以下略"

        # 添付ファイルのチェック
        if settings.read_attachments:
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

    @commands.Cog.listener(name="on_voice_state_update")
    async def auto_join(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """設定に基づいてボイスチャンネルへ自動接続する"""
        if member.bot:
            return

        # 誰かがチャンネルに参加したときのみ判定
        if before.channel == after.channel or after.channel is None:
            return

        try:
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
                # 接続処理
                vc = await after.channel.connect()
                # 読み上げチャンネルを記憶
                self.read_channels[member.guild.id] = target_tc_id

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

            # 内部情報のクリア（read_channels など）
            self.read_channels.pop(member.guild.id, None)

            # 切断
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

        # 既にBotが接続している場合のチェック
        if interaction.guild.voice_client:
            embed = discord.Embed(
                title="⚠️ 既に接続しています",
                description=f"既に **{interaction.guild.voice_client.channel.name}** に接続しています。\n先に `/leave` で切断してください。",
                color=discord.Color.orange()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        channel = interaction.user.voice.channel

        try:
            # VC接続を試行
            await channel.connect()

            # 読み上げチャンネルを記憶
            self.read_channels[interaction.guild.id] = interaction.channel.id

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
                # チャンネルの記憶を削除
                self.read_channels.pop(interaction.guild.id, None)

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
            except Exception:
                logger.error(f"[{interaction.guild.id}] エラーメッセージの送信にも失敗しました")

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
            embed = discord.Embed(
                title="❌ 変換エラー",
                description="読み方の変換中にエラーが発生しました。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

        # 最終チェック
        if not is_katakana(normalized_reading):
            embed = discord.Embed(
                title="❌ 入力エラー",
                description="読み方は「ひらがな」または「カタカナ」で入力してください。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

        if not word:
            embed = discord.Embed(
                title="❌ 入力エラー",
                description="単語を入力してください。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

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
            embed = discord.Embed(
                title="🏠 サーバー辞書に登録しました",
                description=f"`{word}` → `{normalized_reading}`",
                color=discord.Color.green()
            )
            return await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書登録に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ 辞書への登録に失敗しました",
                description="辞書への登録中にエラーが発生しました。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(
                embed=embed,
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
            embed = discord.Embed(
                title="❌ 辞書の取得エラー",
                description="辞書の取得中にエラーが発生しました。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 辞書が存在しない、または空の場合
        if not words_dict or not isinstance(words_dict, dict):
            embed = discord.Embed(
                title="⚠️ 単語が見つかりません",
                description=f"`{word}` は辞書に登録されていません。",
                color=discord.Color.orange()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 削除する単語が辞書に存在するかチェック
        if word not in words_dict:
            embed = discord.Embed(
                title="⚠️ 単語が見つかりません",
                description=f"`{word}` は辞書に登録されていません。",
                color=discord.Color.orange()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 辞書から単語を削除
        try:
            del words_dict[word]
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書からの単語削除に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ 辞書の更新エラー",
                description="辞書の更新中にエラーが発生しました。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        # 更新された辞書をDBに保存
        try:
            success = await self.bot.db.add_or_update_dict(interaction.guild.id, words_dict)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書の保存に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ 辞書の保存エラー",
                description="辞書の保存中にエラーが発生しました。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        if success:
            logger.success(f"[{interaction.guild.id}] 辞書削除: {word}")
            embed = discord.Embed(
                title="🗑️ 辞書から削除しました",
                description=f"`{word}` を辞書から削除しました。",
                color=discord.Color.green()
            )
            return await interaction.response.send_message(embed=embed)
        else:
            logger.warning(f"[{interaction.guild.id}] 辞書削除に失敗しました: {word}")
            embed = discord.Embed(
                title="⚠️ 削除失敗",
                description="削除に失敗しました。",
                color=discord.Color.orange()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="dictionary", description="辞書に登録されている単語一覧を表示します")
    async def dictionary(self, interaction: discord.Interaction):
        try:
            guild_rows = await self.bot.db.get_dict(interaction.guild.id)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書の取得に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ 辞書の取得エラー",
                description="辞書の取得中にエラーが発生しました。",
                color=discord.Color.red()
            )
            return await interaction.response.send_message(embed=embed, ephemeral=True)

        try:
            embed = discord.Embed(title="📖 辞書一覧", color=discord.Color.blue())
            embed.add_field(name="🏠 サーバー辞書", value=format_rows(guild_rows), inline=False)

            await interaction.response.send_message(embed=embed)
        except Exception as e:
            logger.error(f"辞書一覧の送信に失敗しました: {e}")
            embed = discord.Embed(
                title="❌ 辞書の表示エラー",
                description="辞書一覧の表示中にエラーが発生しました。",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)

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
            embed = self.create_config_embed(interaction.guild, settings)
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

    def create_config_embed(self, guild, settings):
        """設定用Embedを生成する共通メソッド"""
        embed = discord.Embed(
            title="⚙️ サーバー設定",
            description=f"現在の設定値は以下の通りです。変更するには下のメニューから項目を選択してください。\n"
                        f"※**{self.bot.user.name}** インスタンスの設定を表示しています。",
            color=discord.Color.blue()
        )

        # 基本設定
        embed.add_field(name="文字数制限", value=f"📝 `{settings.max_chars}` 文字", inline=True)
        embed.add_field(name="さん付け", value="✅ 有効" if settings.add_suffix else "❌ 無効", inline=True)
        embed.add_field(name="ローマ字読み", value="✅ 有効" if settings.read_romaji else "❌ 無効", inline=True)

        embed.add_field(name="メンション", value="✅ 有効" if settings.read_mention else "❌ 無効", inline=True)
        embed.add_field(name="添付ファイル", value="✅ 有効" if settings.read_attachments else "❌ 無効", inline=True)
        embed.add_field(name="入退出通知", value="✅ 有効" if settings.read_vc_status else "❌ 無効", inline=True)

        embed.add_field(name="絵文字の読み上げ", value="✅ 有効" if settings.read_emoji else "❌ 無効", inline=True)
        embed.add_field(name="コードブロックの省略", value="✅ 有効" if settings.skip_code_blocks else "❌ 無効", inline=True)
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
