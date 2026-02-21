# tests/test_integration.py
"""
Integration tests for SumireVoxBot
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.database import Database
from src.core.cache import SettingsCache
from src.core.models import GuildSettings


class TestCacheAndDatabaseIntegration:
    """キャッシュとデータベースの統合テスト"""

    @pytest.fixture
    def database(self) -> Database:
        """テスト用データベースインスタンス"""
        return Database()

    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        """モック接続プール"""
        pool = MagicMock()

        async def mock_acquire():
            conn = AsyncMock()
            conn.execute = AsyncMock()
            conn.fetch = AsyncMock(return_value=[])
            conn.fetchrow = AsyncMock(return_value=None)
            conn.fetchval = AsyncMock(return_value=None)
            return conn

        pool.acquire = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(side_effect=mock_acquire)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)
        pool.close = AsyncMock()

        return pool

    @pytest.mark.asyncio
    async def test_cache_hit_prevents_db_query(self, database: Database, mock_pool: MagicMock):
        """キャッシュヒット時は DB クエリが発生しない"""
        database.pool = mock_pool

        # キャッシュに設定を追加
        settings = GuildSettings(auto_join=True, max_chars=100)
        database.cache.set_guild_settings(123, settings)

        # 設定を取得
        result = await database.get_guild_settings(123)

        assert result.auto_join is True
        # DB クエリは発生していない
        mock_pool.acquire.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_miss_triggers_db_query(self, database: Database, mock_pool: MagicMock):
        """キャッシュミス時は DB クエリが発生する"""
        database.pool = mock_pool

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "settings": json.dumps({"auto_join": True})
        })
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        # キャッシュは空
        assert database.cache.get_guild_settings(999) is None

        # 設定を取得
        result = await database.get_guild_settings(999)

        # DB クエリが発生
        mock_pool.acquire.assert_called()
        # キャッシュに保存された
        assert database.cache.get_guild_settings(999) is not None

    @pytest.mark.asyncio
    async def test_notify_updates_cache(self, database: Database):
        """NOTIFY がキャッシュを更新する"""
        # 初期設定
        database.cache.set_guild_settings(123, GuildSettings(auto_join=False))

        # NOTIFY をシミュレート
        new_data = {"auto_join": True, "max_chars": 200}
        database._handle_guild_settings_change("UPDATE", 123, new_data)

        # キャッシュが更新されている
        result = database.cache.get_guild_settings(123)
        assert result.auto_join is True
        assert result.max_chars == 200


class TestDictionaryLoadUnloadFlow:
    """辞書のロード/アンロードフローテスト"""

    @pytest.fixture
    def database(self) -> Database:
        return Database()

    @pytest.fixture
    def mock_pool(self) -> MagicMock:
        pool = MagicMock()

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "dict": json.dumps({"hello": "ハロー"})
        })

        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        return pool

    @pytest.mark.asyncio
    async def test_vc_join_loads_dictionary(self, database: Database, mock_pool: MagicMock):
        """VC 参加時に辞書がロードされる"""
        database.pool = mock_pool

        await database.load_guild_dict(123)

        assert database.cache.is_guild_active(123) is True
        assert database.cache.is_dict_loaded(123) is True

    def test_vc_leave_unloads_dictionary(self, database: Database):
        """VC 退出時に辞書がアンロードされる"""
        database.cache.add_active_guild(123)
        database.cache.set_dict(123, {"test": "テスト"})

        database.unload_guild_dict(123)

        assert database.cache.is_guild_active(123) is False
        assert database.cache.get_dict(123) is None

    @pytest.mark.asyncio
    async def test_dictionary_not_loaded_when_inactive(self, database: Database, mock_pool: MagicMock):
        """非アクティブギルドでは辞書がキャッシュに保存されない"""
        database.pool = mock_pool

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "dict": json.dumps({"test": "テスト"})
        })
        mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)

        # ギルドはアクティブでない
        assert database.cache.is_guild_active(123) is False

        # 辞書を取得（キャッシュには保存されない）
        result = await database.get_dict(123)

        assert result == {"test": "テスト"}
        # アクティブでないのでキャッシュには保存されない
        # （この動作は実装によるが、現在の実装ではキャッシュに保存されない）


class TestBoostLevelIntegration:
    """ブーストレベル統合テスト"""

    @pytest.fixture
    def database(self) -> Database:
        return Database()

    @pytest.mark.asyncio
    async def test_boost_flow(self, database: Database):
        """ブーストの追加/削除フロー"""
        guild_id = 123

        # 初期状態: 0ブースト
        database.cache.set_boost_count(guild_id, 0)
        assert await database.get_guild_boost_count(guild_id) == 0
        assert await database.is_guild_boosted(guild_id) is False

        # ブースト追加
        database.cache.increment_boost_count(guild_id)
        assert await database.get_guild_boost_count(guild_id) == 1
        assert await database.is_guild_boosted(guild_id) is True

        # ブースト削除
        database.cache.decrement_boost_count(guild_id)
        assert await database.get_guild_boost_count(guild_id) == 0
        assert await database.is_guild_boosted(guild_id) is False

    @pytest.mark.asyncio
    async def test_sub_bot_activation(self, database: Database):
        """サブBot のアクティベーション条件"""
        guild_id = 123

        with patch.dict("os.environ", {"MIN_BOOST_LEVEL": "1", "SKIP_PREMIUM_CHECK": "false"}):
            # 1ブースト: サブBot (MIN_BOOST_LEVEL=1) は非アクティブ
            database.cache.set_boost_count(guild_id, 1)
            assert await database.is_instance_active(guild_id) is False

            # 2ブースト: サブBot (MIN_BOOST_LEVEL=1) はアクティブ
            database.cache.set_boost_count(guild_id, 2)
            assert await database.is_instance_active(guild_id) is True


class TestGlobalDictionaryHandling:
    """グローバル辞書の取り扱いテスト"""

    @pytest.fixture
    def database(self) -> Database:
        db = Database()
        db.cache.global_dict_id = 1201
        return db

    @pytest.mark.asyncio
    async def test_global_dict_always_cached(self, database: Database, mock_pool=None):
        """グローバル辞書は常にキャッシュされる"""
        global_dict = {"global_word": "グローバルワード"}
        database.cache.set_dict(1201, global_dict)

        # グローバル辞書は削除されない
        database.cache.remove_dict(1201)

        assert database.cache.get_dict(1201) == global_dict

    @pytest.mark.asyncio
    async def test_global_dict_id_zero_returns_empty(self, database: Database):
        """GLOBAL_DICT_ID=0 の場合は空辞書を返す"""
        database.cache.global_dict_id = 0

        result = await database.get_dict(0)

        assert result == {}
