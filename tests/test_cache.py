# tests/test_cache.py
"""
Tests for SettingsCache
"""

import pytest
from src.core.cache import SettingsCache
from src.core.models import GuildSettings


class TestSettingsCache:
    """SettingsCache クラスのテスト"""

    @pytest.fixture
    def cache(self) -> SettingsCache:
        """新しいキャッシュインスタンスを作成"""
        return SettingsCache()

    # ========================================
    # 初期化テスト
    # ========================================
    def test_initialization(self, cache: SettingsCache):
        """初期化が正しく行われることを確認"""
        assert cache.guild_settings == {}
        assert cache.user_settings == {}
        assert cache.boost_counts == {}
        assert cache.dictionaries == {}
        assert cache.active_voice_guilds == set()
        assert cache.pending_dict_reload == set()
        assert cache.global_dict_id == 0
        assert cache.is_initialized is False

    # ========================================
    # ギルド設定テスト
    # ========================================
    def test_guild_settings_set_and_get(self, cache: SettingsCache):
        """ギルド設定の保存と取得"""
        settings = GuildSettings(auto_join=True, max_chars=100)
        cache.set_guild_settings(123, settings)

        result = cache.get_guild_settings(123)
        assert result is not None
        assert result.auto_join is True
        assert result.max_chars == 100

    def test_guild_settings_get_nonexistent(self, cache: SettingsCache):
        """存在しないギルド設定の取得"""
        result = cache.get_guild_settings(999)
        assert result is None

    def test_guild_settings_invalidate(self, cache: SettingsCache):
        """ギルド設定の無効化"""
        settings = GuildSettings()
        cache.set_guild_settings(123, settings)
        cache.invalidate_guild_settings(123)

        assert cache.get_guild_settings(123) is None

    def test_guild_settings_type_conversion(self, cache: SettingsCache):
        """guild_id の型変換テスト"""
        settings = GuildSettings()
        cache.set_guild_settings("123", settings)  # 文字列で渡す

        result = cache.get_guild_settings(123)  # 整数で取得
        assert result is not None

    # ========================================
    # ユーザー設定テスト
    # ========================================
    def test_user_settings_set_and_get(self, cache: SettingsCache):
        """ユーザー設定の保存と取得"""
        settings = {"speaker": 2, "speed": 1.2, "pitch": 0.5}
        cache.set_user_setting(456, settings)

        result = cache.get_user_setting(456)
        assert result == settings

    def test_user_settings_invalidate(self, cache: SettingsCache):
        """ユーザー設定の無効化"""
        cache.set_user_setting(456, {"speaker": 1})
        cache.invalidate_user_setting(456)

        assert cache.get_user_setting(456) is None

    # ========================================
    # ブーストカウントテスト
    # ========================================
    def test_boost_count_set_and_get(self, cache: SettingsCache):
        """ブーストカウントの保存と取得"""
        cache.set_boost_count(123, 3)

        assert cache.get_boost_count(123) == 3

    def test_boost_count_increment(self, cache: SettingsCache):
        """ブーストカウントのインクリメント"""
        cache.set_boost_count(123, 2)
        cache.increment_boost_count(123)

        assert cache.get_boost_count(123) == 3

    def test_boost_count_increment_from_zero(self, cache: SettingsCache):
        """存在しないギルドへのインクリメント"""
        cache.increment_boost_count(999)

        assert cache.get_boost_count(999) == 1

    def test_boost_count_decrement(self, cache: SettingsCache):
        """ブーストカウントのデクリメント"""
        cache.set_boost_count(123, 3)
        cache.decrement_boost_count(123)

        assert cache.get_boost_count(123) == 2

    def test_boost_count_decrement_minimum(self, cache: SettingsCache):
        """ブーストカウントが負にならないことを確認"""
        cache.set_boost_count(123, 0)
        cache.decrement_boost_count(123)

        assert cache.get_boost_count(123) == 0

    # ========================================
    # 辞書テスト
    # ========================================
    def test_dict_set_and_get(self, cache: SettingsCache):
        """辞書の保存と取得"""
        dict_data = {"hello": "ハロー", "world": "ワールド"}
        cache.set_dict(123, dict_data)

        result = cache.get_dict(123)
        assert result == dict_data

    def test_dict_remove(self, cache: SettingsCache):
        """辞書の削除"""
        cache.set_dict(123, {"test": "テスト"})
        cache.remove_dict(123)

        assert cache.get_dict(123) is None

    def test_dict_remove_global_protected(self, cache: SettingsCache):
        """グローバル辞書は削除されないことを確認"""
        cache.global_dict_id = 1201
        cache.set_dict(1201, {"global": "グローバル"})
        cache.remove_dict(1201)

        # グローバル辞書は削除されない
        assert cache.get_dict(1201) is not None

    def test_dict_is_loaded(self, cache: SettingsCache):
        """辞書がロード済みかの確認"""
        assert cache.is_dict_loaded(123) is False

        cache.set_dict(123, {})
        assert cache.is_dict_loaded(123) is True

    def test_dict_pending_reload(self, cache: SettingsCache):
        """再ロード待ちフラグのテスト"""
        cache.set_dict(123, {"test": "テスト"})
        cache.mark_dict_needs_reload(123)

        # 再ロード待ちの場合は None を返す
        assert cache.get_dict(123) is None
        assert cache.is_dict_loaded(123) is False

    def test_dict_reload_clears_pending_flag(self, cache: SettingsCache):
        """set_dict で再ロードフラグがクリアされることを確認"""
        cache.set_dict(123, {"old": "オールド"})
        cache.mark_dict_needs_reload(123)
        cache.set_dict(123, {"new": "ニュー"})

        assert cache.get_dict(123) == {"new": "ニュー"}
        assert 123 not in cache.pending_dict_reload

    def test_dict_mark_nonexistent_does_nothing(self, cache: SettingsCache):
        """存在しない辞書へのマークは何もしない"""
        cache.mark_dict_needs_reload(999)

        # pending_dict_reload には追加されない（辞書が存在しないため）
        assert 999 not in cache.pending_dict_reload

    # ========================================
    # VC接続状態テスト
    # ========================================
    def test_active_guild_add_and_check(self, cache: SettingsCache):
        """アクティブギルドの追加と確認"""
        assert cache.is_guild_active(123) is False

        cache.add_active_guild(123)
        assert cache.is_guild_active(123) is True

    def test_active_guild_remove(self, cache: SettingsCache):
        """アクティブギルドの削除"""
        cache.add_active_guild(123)
        cache.remove_active_guild(123)

        assert cache.is_guild_active(123) is False

    def test_active_guild_remove_nonexistent(self, cache: SettingsCache):
        """存在しないギルドの削除（エラーにならない）"""
        cache.remove_active_guild(999)  # エラーにならないことを確認

    # ========================================
    # 統計テスト
    # ========================================
    def test_stats(self, cache: SettingsCache):
        """統計情報のテスト"""
        cache.set_guild_settings(1, GuildSettings())
        cache.set_guild_settings(2, GuildSettings())
        cache.set_user_setting(1, {})
        cache.set_boost_count(1, 3)
        cache.set_dict(1, {})
        cache.add_active_guild(1)

        # 存在する辞書に対してマークする
        cache.set_dict(999, {"temp": "テンプ"})
        cache.mark_dict_needs_reload(999)

        stats = cache.stats()

        assert stats["guild_settings"] == 2
        assert stats["user_settings"] == 1
        assert stats["boost_counts"] == 1
        assert stats["dictionaries_loaded"] == 2  # 1 と 999
        assert stats["active_voice_guilds"] == 1
        assert stats["pending_dict_reload"] == 1

    def test_stats_empty(self, cache: SettingsCache):
        """空のキャッシュの統計"""
        stats = cache.stats()

        assert stats["guild_settings"] == 0
        assert stats["user_settings"] == 0
        assert stats["boost_counts"] == 0
        assert stats["dictionaries_loaded"] == 0
        assert stats["active_voice_guilds"] == 0
        assert stats["pending_dict_reload"] == 0
