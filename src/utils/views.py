import discord
from src.utils.logger import logger


# 数値入力用のモーダル（既存のものをシンプルに修正）
class ConfigEditModal(discord.ui.Modal):
    def __init__(self, item_name: str, item_key: str, current_value: int, db):
        super().__init__(title=f"{item_name} の設定")
        self.item_key = item_key
        self.db = db

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

        try:
            setattr(settings, self.item_key, new_value)
            await self.db.set_guild_settings(interaction.guild.id, settings)
            await interaction.response.send_message(f"✅ 設定を更新しました：`{old_value}` ➡ **`{new_value}`**",
                                                    ephemeral=True)
        except Exception as e:
            logger.error(f"Config update failed: {e}")
            await interaction.response.send_message(f"❌ 更新に失敗しました: {e}", ephemeral=True)


# ON/OFF 選択用の View
class ConfigToggleView(discord.ui.View):
    def __init__(self, item_name: str, item_key: str, db):
        super().__init__(timeout=60)
        self.item_name = item_name
        self.item_key = item_key
        self.db = db

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

        status_text = "有効" if new_value else "無効"
        await interaction.response.send_message(
            f"✅ **{self.item_name}** を **{status_text}** に設定しました。",
            ephemeral=True
        )


# メインの項目選択 View
class ConfigSearchView(discord.ui.View):
    def __init__(self, db):
        super().__init__(timeout=180)
        self.db = db

    @discord.ui.select(
        placeholder="設定する項目を選んでください",
        options=[
            discord.SelectOption(label="自動接続", value="auto_join", description="VCへの自動参加設定"),
            discord.SelectOption(label="文字数制限", value="max_chars", description="読み上げる最大文字数 (10-500)"),
            discord.SelectOption(label="入退出の読み上げ", value="read_vc_status",
                                 description="ユーザーの入退室を通知"),
            discord.SelectOption(label="メンション読み上げ", value="read_mention",
                                 description="メンションを読み上げるか"),
            discord.SelectOption(label="さん付け", value="add_suffix", description="名前に「さん」を付けるか"),
            discord.SelectOption(label="ローマ字読み", value="read_romaji", description="ローマ字をそのまま読むか"),
            discord.SelectOption(label="添付ファイルの読み上げ", value="read_attachments",
                                 description="ファイル名を読み上げるか"),
            discord.SelectOption(label="コードブロックの省略", value="skip_code_blocks",
                                 description="コードをスキップするか"),
            discord.SelectOption(label="URLの省略", value="skip_urls", description="URLを省略して読むか"),
        ]
    )
    async def select_item(self, interaction: discord.Interaction, select: discord.ui.Select):
        item_key = select.values[0]
        item_label = [opt.label for opt in select.options if opt.value == item_key][0]

        settings = await self.db.get_guild_settings(interaction.guild.id)
        current_value = getattr(settings, item_key)

        # 型に基づいて出し分ける
        if isinstance(current_value, bool):
            # ON/OFF 選択用の View を送る
            await interaction.response.send_message(
                f"**{item_label}** の設定を切り替えます：",
                view=ConfigToggleView(item_label, item_key, self.db),
                ephemeral=True
            )
        else:
            # 数値なら Modal を出す
            await interaction.response.send_modal(
                ConfigEditModal(item_label, item_key, current_value, self.db)
            )