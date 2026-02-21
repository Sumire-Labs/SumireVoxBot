# tests/test_models.py
"""
Tests for Pydantic models
"""

import pytest
from pydantic import ValidationError
from src.core.models import GuildSettings, GuildDict, GuildBoost, UserBilling


class TestGuildSettings:
    """GuildSettings モデルのテスト"""

    def test_default_values(self):
        """デフォルト値が正しく設定されることを確認"""
        settings = GuildSettings()

        assert settings.auto_join is False
        assert settings.auto_join_config == {}
        assert settings.max_chars == 50
        assert settings.read_vc_status is False
        assert settings.read_mention is True
        assert settings.read_emoji is True
        assert settings.add_suffix is False
        assert settings.read_romaji is False
        assert settings.read_attachments is True
        assert settings.skip_code_blocks is True
        assert settings.skip_urls is True

    def test_custom_values(self):
        """カスタム値が正しく設定されることを確認"""
        settings = GuildSettings(
            auto_join=True,
            max_chars=100,
            read_vc_status=True,
            add_suffix=True
        )

        assert settings.auto_join is True
        assert settings.max_chars == 100
        assert settings.read_vc_status is True
        assert settings.add_suffix is True

    def test_max_chars_validation_min(self):
        """max_chars の最小値バリデーション"""
        with pytest.raises(ValidationError):
            GuildSettings(max_chars=5)  # 最小値は10

    def test_max_chars_validation_max(self):
        """max_chars の最大値バリデーション"""
        with pytest.raises(ValidationError):
            GuildSettings(max_chars=600)  # 最大値は500

    def test_max_chars_boundary_values(self):
        """max_chars の境界値テスト"""
        settings_min = GuildSettings(max_chars=10)
        settings_max = GuildSettings(max_chars=500)

        assert settings_min.max_chars == 10
        assert settings_max.max_chars == 500

    def test_auto_join_config_structure(self):
        """auto_join_config の構造テスト"""
        config = {
            "123456": {"voice": 111, "text": 222},
            "789012": {"voice": 333, "text": 444}
        }
        settings = GuildSettings(auto_join_config=config)

        assert "123456" in settings.auto_join_config
        assert settings.auto_join_config["123456"]["voice"] == 111

    def test_model_dump(self):
        """model_dump() が正しく動作することを確認"""
        settings = GuildSettings(auto_join=True, max_chars=100)
        data = settings.model_dump()

        assert isinstance(data, dict)
        assert data["auto_join"] is True
        assert data["max_chars"] == 100

    def test_model_validate(self):
        """model_validate() が正しく動作することを確認"""
        data = {
            "auto_join": True,
            "max_chars": 150,
            "read_mention": False
        }
        settings = GuildSettings.model_validate(data)

        assert settings.auto_join is True
        assert settings.max_chars == 150
        assert settings.read_mention is False


class TestGuildDict:
    """GuildDict モデルのテスト"""

    def test_valid_dict_entry(self):
        """有効な辞書エントリ"""
        entry = GuildDict(word="東京", reading="トウキョウ")

        assert entry.word == "東京"
        assert entry.reading == "トウキョウ"

    def test_required_fields(self):
        """必須フィールドのテスト"""
        with pytest.raises(ValidationError):
            GuildDict()  # word と reading は必須


class TestGuildBoost:
    """GuildBoost モデルのテスト"""

    def test_valid_boost(self):
        """有効なブーストエントリ"""
        boost = GuildBoost(id=1, guild_id=123456789, user_id="987654321")

        assert boost.id == 1
        assert boost.guild_id == 123456789
        assert boost.user_id == "987654321"


class TestUserBilling:
    """UserBilling モデルのテスト"""

    def test_default_values(self):
        """デフォルト値のテスト"""
        billing = UserBilling(discord_id="123456789")

        assert billing.discord_id == "123456789"
        assert billing.stripe_customer_id is None
        assert billing.total_slots == 0
        assert billing.boosts == []

    def test_with_boosts(self):
        """ブースト付きのテスト"""
        boosts = [
            GuildBoost(id=1, guild_id=111, user_id="123"),
            GuildBoost(id=2, guild_id=222, user_id="123")
        ]
        billing = UserBilling(
            discord_id="123456789",
            total_slots=3,
            boosts=boosts
        )

        assert billing.total_slots == 3
        assert len(billing.boosts) == 2
