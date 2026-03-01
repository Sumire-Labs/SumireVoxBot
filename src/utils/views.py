import discord
from src.utils.logger import logger

# 1ページあたりの表示件数
DICTIONARY_PAGE_SIZE = 20


async def update_config_message(bot, interaction, settings, original_message):
    """元の設定メッセージのEmbedを最新の状態に更新する共通処理"""
    voice_cog = bot.get_cog("Voice")
    if voice_cog and original_message:
        try:
            is_boosted = await bot.db.is_guild_boosted(interaction.guild.id)
            new_embed = voice_cog.create_config_embed(interaction.guild, settings, is_boosted)
            await original_message.edit(embed=new_embed)
        except Exception as e:
            logger.error(f"config embedの更新に失敗しました: {e}")


# 数値入力用のモーダル
class ConfigEditModal(discord.ui.Modal):
    def __init__(self, item_name: str, item_key: str, current_value: int, db, bot, original_message):
        super().__init__(title=f"{item_name} の設定")
        self.item_key = item_key
        self.db = db
        self.bot = bot
        self.original_message = original_message

        self.value_input = discord.ui.TextInput(
            label="数値を入力してください",
            default=str(current_value),
            placeholder="例: 100",
            min_length=1,
            max_length=3,
            required=True
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.value_input.value
        if not value.isdigit():
            return await interaction.response.send_message("❌ 数値を入力してください。", ephemeral=True)

        new_value = int(value)
        settings = await self.db.get_guild_settings(interaction.guild.id)
        old_value = getattr(settings, self.item_key)

        is_boosted = await self.db.is_guild_boosted(interaction.guild.id)
        if int(value) > 50:
            if not is_boosted:
                return await interaction.response.send_message("❌ サーバーがブーストされていません。", ephemeral=True)

        try:
            setattr(settings, self.item_key, new_value)
            await self.db.set_guild_settings(interaction.guild.id, settings)

            await update_config_message(self.bot, interaction, settings, self.original_message)

            await interaction.response.send_message(f"✅ 設定を更新しました：`{old_value}` ➡ **`{new_value}`**",
                                                    ephemeral=True)
        except Exception as e:
            logger.error(f"Config update failed: {e}")
            await interaction.response.send_message(f"❌ 更新に失敗しました: {e}", ephemeral=True)


# ON/OFF 選択用の View
class ConfigToggleView(discord.ui.View):
    def __init__(self, item_name: str, item_key: str, db, bot, original_message):
        super().__init__(timeout=60)
        self.item_name = item_name
        self.item_key = item_key
        self.db = db
        self.bot = bot
        self.original_message = original_message

    @discord.ui.select(
        placeholder="状態を選択してください",
        options=[
            discord.SelectOption(label="有効 (ON)", value="True", emoji="✅"),
            discord.SelectOption(label="無効 (OFF)", value="False", emoji="❌"),
        ]
    )
    async def select_toggle(self, interaction: discord.Interaction, select: discord.ui.Select):
        new_value = select.values[0] == "True"
        settings = await self.db.get_guild_settings(interaction.guild.id)
        old_value = getattr(settings, self.item_key)

        setattr(settings, self.item_key, new_value)
        await self.db.set_guild_settings(interaction.guild.id, settings)

        await update_config_message(self.bot, interaction, settings, self.original_message)

        status_text = "有効" if new_value else "無効"
        await interaction.response.send_message(
            f"✅ **{self.item_name}** を **{status_text}** に設定しました。",
            ephemeral=True
        )


# 自動接続設定用の View
class ConfigAutoJoinView(discord.ui.View):
    def __init__(self, db, bot, original_message):
        super().__init__(timeout=180)
        self.db = db
        self.bot = bot
        self.original_message = original_message
        self.selected_vc = None
        self.selected_tc = None

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.voice],
        placeholder="1. 監視するボイスチャンネルを選択",
    )
    async def select_vc(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.selected_vc = select.values[0]
        await interaction.response.send_message(f"✅ 監視対象を {self.selected_vc.mention} に指定しました。",
                                                ephemeral=True)

    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        placeholder="2. 読み上げるテキストチャンネルを選択",
    )
    async def select_tc(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        self.selected_tc = select.values[0]
        await interaction.response.send_message(f"✅ 読み上げ先を {self.selected_tc.mention} に指定しました。",
                                                ephemeral=True)

    @discord.ui.button(label="このBotの設定として保存", style=discord.ButtonStyle.success, emoji="🤖")
    async def save_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.selected_vc or not self.selected_tc:
            return await interaction.response.send_message("❌ VCとTCの両方を選択してください。", ephemeral=True)

        settings = await self.db.get_guild_settings(interaction.guild.id)
        if settings.auto_join_config is None:
            settings.auto_join_config = {}

        bot_key = str(self.bot.user.id)
        settings.auto_join_config[bot_key] = {
            "voice": self.selected_vc.id,
            "text": self.selected_tc.id
        }
        settings.auto_join = True

        await self.db.set_guild_settings(interaction.guild.id, settings)

        await update_config_message(self.bot, interaction, settings, self.original_message)

        return await interaction.response.send_message(
            f"✅ **{self.bot.user.name}** の自動接続設定を保存しました！",
            ephemeral=True
        )

    @discord.ui.button(label="設定を削除", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def delete_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        settings = await self.db.get_guild_settings(interaction.guild.id)

        if settings.auto_join_config is None:
            return await interaction.response.send_message(
                "❌ このBotの自動接続設定は登録されていません。",
                ephemeral=True
            )

        bot_key = str(self.bot.user.id)

        if bot_key not in settings.auto_join_config:
            return await interaction.response.send_message(
                "❌ このBotの自動接続設定は登録されていません。",
                ephemeral=True
            )

        del settings.auto_join_config[bot_key]

        if not settings.auto_join_config:
            settings.auto_join = False

        await self.db.set_guild_settings(interaction.guild.id, settings)

        await update_config_message(self.bot, interaction, settings, self.original_message)

        return await interaction.response.send_message(
            f"✅ **{self.bot.user.name}** の自動接続設定を削除しました。",
            ephemeral=True
        )


# メインの項目選択 View
class ConfigSearchView(discord.ui.View):
    def __init__(self, db, bot):
        super().__init__(timeout=180)
        self.db = db
        self.bot = bot
        self.message: None | discord.Message = None

    @discord.ui.select(
        placeholder="設定する項目を選んでください",
        options=[
            discord.SelectOption(label="自動接続（Bot個別設定）", value="auto_join",
                                 description="どのVCを監視し、どのTCで読み上げるか", emoji="🤖"),
            discord.SelectOption(label="文字数制限", value="max_chars", description="読み上げる最大文字数 (10-500)",
                                 emoji="📝"),
            discord.SelectOption(label="入退出通知", value="read_vc_status", description="ユーザーの入退室を通知",
                                 emoji="🚪"),
            discord.SelectOption(label="メンション", value="read_mention", description="メンションを名前で読み上げるか",
                                 emoji="🆔"),
            discord.SelectOption(label="さん付け", value="add_suffix", description="名前に「さん」を付けるか",
                                 emoji="🎀"),
            discord.SelectOption(label="ローマ字読み", value="read_romaji", description="ローマ字をそのまま読むか",
                                 emoji="🔤"),
            discord.SelectOption(label="添付ファイル", value="read_attachments", description="ファイル名を読み上げるか",
                                 emoji="📎"),
            discord.SelectOption(label="絵文字", value="read_emoji", description="絵文字を読み上げるか",
                                 emoji="😀"),
            discord.SelectOption(label="コードブロック", value="skip_code_blocks", description="コードをスキップするか",
                                 emoji="💻"),
            discord.SelectOption(label="URL省略", value="skip_urls", description="URLを省略して読むか",
                                 emoji="🔗"),
            discord.SelectOption(label="設定パネルを閉じる", value="close", description="このメッセージを削除します",
                                 emoji="🗑️")
        ]
    )
    async def select_item(self, interaction: discord.Interaction, select: discord.ui.Select):
        item_key = select.values[0]

        if item_key == "close":
            try:
                await interaction.message.delete()
            except Exception:
                await interaction.response.edit_message(content="✅ パネルを閉じました。", embed=None, view=None)
            return None

        if item_key == "auto_join":
            is_boosted = await self.db.is_guild_boosted(interaction.guild.id)
            if not is_boosted:
                return await interaction.response.send_message("❌ サーバーがブーストされていません。", ephemeral=True)
            return await interaction.response.send_message(
                "### 🤖 自動接続の個別設定\n監視するVCと出力先のTCを選択してください。",
                view=ConfigAutoJoinView(self.db, self.bot, self.message),
                ephemeral=True
            )

        settings = await self.db.get_guild_settings(interaction.guild.id)
        current_value = getattr(settings, item_key)
        item_label = [opt.label for opt in select.options if opt.value == item_key][0]

        if isinstance(current_value, bool):
            return await interaction.response.send_message(
                f"**{item_label}** の切り替え：",
                view=ConfigToggleView(item_label, item_key, self.db, self.bot, self.message),
                ephemeral=True
            )
        else:
            return await interaction.response.send_modal(
                ConfigEditModal(item_label, item_key, current_value, self.db, self.bot, self.message)
            )


def create_dictionary_embed(words_dict: dict, page: int = 0) -> discord.Embed:
    """辞書のEmbedを作成する（ページネーション対応）"""
    if not words_dict:
        embed = discord.Embed(
            title="📖 サーバー辞書",
            description="登録されている単語はありません。",
            color=discord.Color.blue()
        )
        embed.set_footer(text="0 件登録")
        return embed

    items = sorted(words_dict.items(), key=lambda x: x[0])
    total_items = len(items)
    total_pages = max(1, (total_items + DICTIONARY_PAGE_SIZE - 1) // DICTIONARY_PAGE_SIZE)

    page = max(0, min(page, total_pages - 1))

    start_idx = page * DICTIONARY_PAGE_SIZE
    end_idx = min(start_idx + DICTIONARY_PAGE_SIZE, total_items)
    page_items = items[start_idx:end_idx]

    description = "\n".join(f"・`{word}` → `{reading}`" for word, reading in page_items)

    embed = discord.Embed(
        title="📖 サーバー辞書",
        description=description,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"{total_items} 件登録 | ページ {page + 1}/{total_pages}")

    return embed


# 辞書管理用の View（ページネーション対応）
class DictionaryView(discord.ui.View):
    def __init__(self, db, bot, words_dict: dict | None = None):
        super().__init__(timeout=180)
        self.db = db
        self.bot = bot
        self.message: discord.Message | None = None
        self.words_dict: dict = words_dict if words_dict else {}
        self.current_page: int = 0
        self._update_buttons()

    def _get_total_pages(self) -> int:
        if not self.words_dict:
            return 1
        return max(1, (len(self.words_dict) + DICTIONARY_PAGE_SIZE - 1) // DICTIONARY_PAGE_SIZE)

    def _update_buttons(self):
        total_pages = self._get_total_pages()
        self.first_button.disabled = self.current_page <= 0
        self.prev_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= total_pages - 1
        self.last_button.disabled = self.current_page >= total_pages - 1

    async def _refresh_dict(self, guild_id: int):
        words_dict = await self.db.get_dict(guild_id)
        self.words_dict = words_dict if isinstance(words_dict, dict) else {}
        total_pages = self._get_total_pages()
        if self.current_page >= total_pages:
            self.current_page = max(0, total_pages - 1)

    async def _update_message(self, interaction: discord.Interaction):
        self._update_buttons()
        embed = create_dictionary_embed(self.words_dict, self.current_page)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="≪", style=discord.ButtonStyle.secondary, row=0)
    async def first_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        await self._update_message(interaction)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        await self._update_message(interaction)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(self._get_total_pages() - 1, self.current_page + 1)
        await self._update_message(interaction)

    @discord.ui.button(label="≫", style=discord.ButtonStyle.secondary, row=0)
    async def last_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = self._get_total_pages() - 1
        await self._update_message(interaction)

    @discord.ui.button(label="追加", style=discord.ButtonStyle.success, emoji="➕", row=1)
    async def add_word_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DictionaryAddModal(self.db, self.bot, self))

    @discord.ui.button(label="削除", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def remove_word_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(DictionaryRemoveModal(self.db, self.bot, self))

    @discord.ui.button(label="閉じる", style=discord.ButtonStyle.secondary, emoji="❌", row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.message.delete()


class DictionaryAddModal(discord.ui.Modal):
    def __init__(self, db, bot, dictionary_view: DictionaryView):
        super().__init__(title="単語を追加")
        self.db = db
        self.bot = bot
        self.dictionary_view = dictionary_view

        self.word_input = discord.ui.TextInput(
            label="登録する単語",
            placeholder="例: 東京",
            min_length=1,
            max_length=50,
            required=True
        )
        self.reading_input = discord.ui.TextInput(
            label="読み方（ひらがな または カタカナ）",
            placeholder="例: とうきょう",
            min_length=1,
            max_length=50,
            required=True
        )
        self.add_item(self.word_input)
        self.add_item(self.reading_input)

    async def on_submit(self, interaction: discord.Interaction):
        import jaconv
        import re

        word = self.word_input.value.strip()
        reading = self.reading_input.value.strip()

        def is_katakana(text: str) -> bool:
            return re.fullmatch(r'^[ァ-ヶーヴ]+$', text) is not None

        try:
            normalized_reading = jaconv.h2z(reading, kana=True, digit=False, ascii=False)
            normalized_reading = jaconv.hira2kata(normalized_reading)
        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 読み方の正規化に失敗しました: {e}")
            return await interaction.response.send_message(
                embed=discord.Embed(title="❌ 変換エラー", description="読み方の変換中にエラーが発生しました。", color=discord.Color.red()),
                ephemeral=True
            )

        if not is_katakana(normalized_reading):
            return await interaction.response.send_message(
                embed=discord.Embed(title="❌ 入力エラー", description="読み方は「ひらがな」または「カタカナ」で入力してください。", color=discord.Color.red()),
                ephemeral=True
            )

        if not word:
            return await interaction.response.send_message(
                embed=discord.Embed(title="❌ 入力エラー", description="単語を入力してください。", color=discord.Color.red()),
                ephemeral=True
            )

        try:
            words_dict = await self.db.get_dict(interaction.guild.id)
            if not words_dict or not isinstance(words_dict, dict):
                words_dict = {}

            is_boosted = await self.bot.db.is_guild_boosted(interaction.guild.id)
            limit = 100 if is_boosted else 10

            if len(words_dict) >= limit and word not in words_dict:
                return await interaction.response.send_message(
                    embed=discord.Embed(
                        title="💎 登録上限エラー",
                        description=f"辞書の登録数が上限に達しています。\n現在のプランの上限: **{limit}** 個\n\n"
                                    f"{'プレミアムプランに加入すると、最大100個まで登録可能です。' if not is_boosted else 'これ以上の登録はできません。'}",
                        color=discord.Color.gold()
                    ),
                    ephemeral=True
                )

            words_dict[word] = normalized_reading
            await self.db.add_or_update_dict(interaction.guild.id, words_dict)

            logger.success(f"[{interaction.guild.id}] 辞書登録: {word} -> {normalized_reading}")
            await interaction.response.send_message(
                embed=discord.Embed(title="✅ 単語を追加しました", description=f"`{word}` → `{normalized_reading}`", color=discord.Color.green()),
                ephemeral=True
            )

            await self._update_dictionary_view(interaction)

        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書登録に失敗しました: {e}")
            return await interaction.response.send_message(
                embed=discord.Embed(title="❌ 登録エラー", description="辞書への登録中にエラーが発生しました。", color=discord.Color.red()),
                ephemeral=True
            )

    async def _update_dictionary_view(self, interaction: discord.Interaction):
        if self.dictionary_view and self.dictionary_view.message:
            try:
                await self.dictionary_view._refresh_dict(interaction.guild.id)
                self.dictionary_view._update_buttons()
                embed = create_dictionary_embed(self.dictionary_view.words_dict, self.dictionary_view.current_page)
                await self.dictionary_view.message.edit(embed=embed, view=self.dictionary_view)
            except Exception as e:
                logger.error(f"辞書 embedの更新に失敗しました: {e}")


class DictionaryRemoveModal(discord.ui.Modal):
    def __init__(self, db, bot, dictionary_view: DictionaryView):
        super().__init__(title="単語を削除")
        self.db = db
        self.bot = bot
        self.dictionary_view = dictionary_view

        self.word_input = discord.ui.TextInput(
            label="削除する単語",
            placeholder="例: 東京",
            min_length=1,
            max_length=50,
            required=True
        )
        self.add_item(self.word_input)

    async def on_submit(self, interaction: discord.Interaction):
        word = self.word_input.value.strip()

        try:
            words_dict = await self.db.get_dict(interaction.guild.id)

            if not words_dict or not isinstance(words_dict, dict) or word not in words_dict:
                return await interaction.response.send_message(
                    embed=discord.Embed(title="⚠️ 単語が見つかりません", description=f"`{word}` は辞書に登録されていません。", color=discord.Color.orange()),
                    ephemeral=True
                )

            del words_dict[word]
            success = await self.db.add_or_update_dict(interaction.guild.id, words_dict)

            if success:
                logger.success(f"[{interaction.guild.id}] 辞書削除: {word}")
                await interaction.response.send_message(
                    embed=discord.Embed(title="✅ 単語を削除しました", description=f"`{word}` を辞書から削除しました。", color=discord.Color.green()),
                    ephemeral=True
                )
                await self._update_dictionary_view(interaction)
            else:
                return await interaction.response.send_message(
                    embed=discord.Embed(title="⚠️ 削除失敗", description="削除に失敗しました。", color=discord.Color.orange()),
                    ephemeral=True
                )

        except Exception as e:
            logger.error(f"[{interaction.guild.id}] 辞書操作中にエラーが発生しました: {e}")
            return await interaction.response.send_message(
                embed=discord.Embed(title="❌ エラー", description="辞書操作中にエラーが発生しました。", color=discord.Color.red()),
                ephemeral=True
            )

    async def _update_dictionary_view(self, interaction: discord.Interaction):
        if self.dictionary_view and self.dictionary_view.message:
            try:
                await self.dictionary_view._refresh_dict(interaction.guild.id)
                self.dictionary_view._update_buttons()
                embed = create_dictionary_embed(self.dictionary_view.words_dict, self.dictionary_view.current_page)
                await self.dictionary_view.message.edit(embed=embed, view=self.dictionary_view)
            except Exception as e:
                logger.error(f"辞書 embedの更新に失敗しました: {e}")


async def update_dictionary_message(bot, interaction, original_message):
    """後方互換用"""
    voice_cog = bot.get_cog("Voice")
    if voice_cog and original_message:
        try:
            words_dict = await voice_cog._get_guild_dict(interaction)
            embed = create_dictionary_embed(words_dict)
            await original_message.edit(embed=embed)
        except Exception as e:
            logger.error(f"辞書 embedの更新に失敗しました: {e}")
