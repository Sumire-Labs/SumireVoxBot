# src/cogs/voice/embeds/create_config_embed.py
import discord


def create_config_embed(bot, guild, settings, is_boosted=False):
    """設定用Embedを生成する共通メソッド"""
    embed = discord.Embed(
        title="⚙️ サーバー設定",
        description=f"現在の設定値は以下の通りです。変更するには下のメニューから項目を選択してください。\n"
                    f"※**{bot.user.name}** インスタンスの設定を表示しています。",
        color=discord.Color.blue()
    )

    # 基本設定
    # 無料: 50文字固定, 1ブースト以上: 設定値（最大200文字）
    if is_boosted:
        effective_limit = min(settings.max_chars, 200)
        char_limit_text = f"📝 `{effective_limit}` 文字 (設定値: {settings.max_chars})"
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
    bot_key = str(bot.user.id)
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
