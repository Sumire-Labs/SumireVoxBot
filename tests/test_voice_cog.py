# tests/test_voice_cog.py
"""
Tests for Voice Cog
"""

import pytest
import re
from unittest.mock import AsyncMock, MagicMock, patch


class TestVoiceCogHelpers:
    """Voice Cog のヘルパー関数テスト"""

    def test_is_katakana_valid(self):
        """有効なカタカナ文字列"""
        from src.cogs.voice import is_katakana

        assert is_katakana("カタカナ") is True
        assert is_katakana("テスト") is True
        assert is_katakana("アイウエオ") is True
        assert is_katakana("ー") is True  # 長音記号
        assert is_katakana("ヴァイオリン") is True

    def test_is_katakana_invalid(self):
        """無効な文字列（カタカナ以外を含む）"""
        from src.cogs.voice import is_katakana

        assert is_katakana("ひらがな") is False
        assert is_katakana("漢字") is False
        assert is_katakana("abc") is False
        assert is_katakana("カタカナとひらがな") is False
        assert is_katakana("") is False

    def test_format_rows_dict(self):
        """辞書形式のフォーマット"""
        from src.cogs.voice import format_rows

        rows = {"hello": "ハロー", "world": "ワールド"}
        result = format_rows(rows)

        assert "hello" in result
        assert "ハロー" in result

    def test_format_rows_empty(self):
        """空の辞書"""
        from src.cogs.voice import format_rows

        result = format_rows({})
        assert result == "登録なし"

    def test_format_rows_none(self):
        """None の場合"""
        from src.cogs.voice import format_rows

        result = format_rows(None)
        assert result == "登録なし"


class TestVoiceCogApplyDictionary:
    """辞書適用のテスト"""

    @pytest.fixture
    def mock_voice_cog(self):
        """モック Voice Cog"""
        from src.cogs.voice import Voice

        mock_bot = MagicMock()
        mock_bot.db = MagicMock()
        mock_bot.db.get_dict = AsyncMock(return_value={})

        with patch.dict("os.environ", {"GLOBAL_DICT_ID": "1201"}):
            cog = Voice(mock_bot)

        return cog

    @pytest.mark.asyncio
    async def test_apply_dictionary_basic(self, mock_voice_cog):
        """基本的な辞書適用"""
        mock_voice_cog.bot.db.get_dict = AsyncMock(return_value={
            "Discord": "ディスコード",
            "Bot": "ボット"
        })

        result = await mock_voice_cog.apply_dictionary("Hello Discord Bot!", 123)

        assert "ディスコード" in result
        assert "ボット" in result

    @pytest.mark.asyncio
    async def test_apply_dictionary_case_insensitive(self, mock_voice_cog):
        """大文字小文字を区別しない置換"""
        mock_voice_cog.bot.db.get_dict = AsyncMock(return_value={
            "discord": "ディスコード"
        })

        result = await mock_voice_cog.apply_dictionary("DISCORD discord Discord", 123)

        # すべて置換される
        assert result.count("ディスコード") == 3

    @pytest.mark.asyncio
    async def test_apply_dictionary_longer_match_first(self, mock_voice_cog):
        """長い単語が先にマッチ"""
        mock_voice_cog.bot.db.get_dict = AsyncMock(return_value={
            "Bot": "ボット",
            "Discord Bot": "ディスコードボット"
        })

        result = await mock_voice_cog.apply_dictionary("Discord Bot", 123)

        # "Discord Bot" が先にマッチする
        assert "ディスコードボット" in result

    @pytest.mark.asyncio
    async def test_apply_dictionary_zero_guild_id(self, mock_voice_cog):
        """guild_id が 0 の場合はスキップ"""
        result = await mock_voice_cog.apply_dictionary("Test content", 0)

        assert result == "Test content"
        mock_voice_cog.bot.db.get_dict.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_dictionary_empty_dict(self, mock_voice_cog):
        """空の辞書の場合は変更なし"""
        mock_voice_cog.bot.db.get_dict = AsyncMock(return_value={})

        result = await mock_voice_cog.apply_dictionary("Test content", 123)

        assert result == "Test content"


class TestVoiceCogTextProcessing:
    """テキスト処理のテスト"""

    def test_discord_timestamp_relative(self):
        """Discord タイムスタンプ (相対) の変換"""
        import re
        from datetime import datetime, timezone

        # 簡易的なテスト用の関数
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
            else:
                n, unit = sec // 86400, "日"

            if n <= 0:
                n = 1

            return f"{n}{unit}{'後' if future else '前'}"

        now = datetime.now(timezone.utc)
        past = datetime.fromtimestamp(now.timestamp() - 3600, tz=timezone.utc)  # 1時間前

        result = _relative_jp(past, now)
        assert "前" in result
        assert "時間" in result

    def test_code_block_removal(self):
        """コードブロックの省略"""
        content = "Here is code: ```python\nprint('hello')\n```"
        result = re.sub(r"```.*?```", "、コードブロック省略、", content, flags=re.DOTALL)

        assert "コードブロック省略" in result
        assert "print" not in result

    def test_inline_code_removal(self):
        """インラインコードの省略"""
        content = "Use `print()` function"
        result = re.sub(r"`.*?`", "、コード省略、", content, flags=re.DOTALL)

        assert "コード省略" in result
        assert "print()" not in result

    def test_url_removal(self):
        """URL の省略"""
        content = "Check https://example.com/path?query=1 for details"
        result = re.sub(r"https?://[\w/:%#$&?()~.=+\-]+", "、ユーアールエル省略、", content)

        assert "ユーアールエル省略" in result
        assert "https://" not in result

    def test_custom_emoji_extraction(self):
        """カスタム絵文字からテキスト抽出"""
        content = "Hello <:emoji_name:123456789>"
        result = re.sub(r"<a?:(\w+):?\d+>", r"\1", content)

        assert result == "Hello emoji_name"

    def test_animated_emoji_extraction(self):
        """アニメーション絵文字からテキスト抽出"""
        content = "Hello <a:animated_emoji:987654321>"
        result = re.sub(r"<a?:(\w+):?\d+>", r"\1", content)

        assert result == "Hello animated_emoji"


class TestAudioTask:
    """AudioTask データクラスのテスト"""

    def test_audio_task_creation(self):
        """AudioTask の作成"""
        from src.cogs.voice import AudioTask

        task = AudioTask(
            task_id="test-uuid",
            text="テストテキスト",
            author_id=123456,
            file_path="/tmp/test.wav"
        )

        assert task.task_id == "test-uuid"
        assert task.text == "テストテキスト"
        assert task.author_id == 123456
        assert task.is_failed is False
        assert task.generation_task is None

    def test_audio_task_event(self):
        """AudioTask の Event 機能"""
        import asyncio
        from src.cogs.voice import AudioTask

        task = AudioTask(
            task_id="test-uuid",
            text="テスト",
            author_id=123,
            file_path="/tmp/test.wav"
        )

        assert not task.is_ready.is_set()

        task.is_ready.set()
        assert task.is_ready.is_set()
