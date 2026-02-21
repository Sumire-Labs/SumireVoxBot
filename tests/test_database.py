# tests/test_database.py
"""
Tests for Database class
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.database import Database
from src.core.models import GuildSettings


class TestDatabase:
    """Database クラスのテスト"""

    @pytest.fixture
    def database(self) -> Database:
        """新しい Database インスタンスを作成"""
        return Database()

    # ========================================
    # 初期化テスト
    # ========================================
    def test_initialization(self, database: Database):
        """初期化が正しく行われることを確認"""
        assert database.pool is None
        assert database.cache is not None
        assert database._listener_connection is None
        assert database._listener_task is None
        assert database._shutdown is False

    # ========================================
    # ギルド設定テスト
    # ========================================
    @pytest.mark.asyncio
    async def test_get_guild_settings_from_cache(self, database: Database):
        """キャッシュからギルド設定を取得"""
        settings = GuildSettings(auto_join=True)
        database.cache.set_guild_settings(123, settings)

        result = await database.get_guild_settings(123)

        assert result.auto_join is True

    @pytest.mark.asyncio
    async def test_get_guild_settings_cache_miss(self, database: Database, mock_asyncpg_pool: MagicMock):
        """キャッシュミス時に DB から取得"""
        database.pool = mock_asyncpg_pool

        # DB からの返却値を設定
        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "settings": json.dumps({"auto_join": True, "max_chars": 100})
        })
        mock_asyncpg_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_asyncpg_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await database.get_guild_settings(123)

        assert result.auto_join is True
        assert result.max_chars == 100
        # キャッシュに保存されたことを確認
        assert database.cache.get_guild_settings(123) is not None

    @pytest.mark.asyncio
    async def test_get_guild_settings_default(self, database: Database, mock_asyncpg_pool: MagicMock):
        """DB にも存在しない場合はデフォルト値を返す"""
        database.pool = mock_asyncpg_pool

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_asyncpg_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_asyncpg_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await database.get_guild_settings(999)

        assert result.auto_join is False  # デフォルト値
        assert result.max_chars == 50  # デフォルト値

    @pytest.mark.asyncio
    async def test_set_guild_settings(self, database: Database, mock_asyncpg_pool: MagicMock):
        """ギルド設定の保存"""
        database.pool = mock_asyncpg_pool

        mock_conn = AsyncMock()
        mock_asyncpg_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_asyncpg_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        settings = GuildSettings(auto_join=True, max_chars=150)
        await database.set_guild_settings(123, settings)

        mock_conn.execute.assert_called_once()

    # ========================================
    # ユーザー設定テスト
    # ========================================
    @pytest.mark.asyncio
    async def test_get_user_setting_from_cache(self, database: Database):
        """キャッシュからユーザー設定を取得"""
        settings = {"speaker": 2, "speed": 1.5, "pitch": 0.3}
        database.cache.set_user_setting(456, settings)

        result = await database.get_user_setting(456)

        assert result["speaker"] == 2
        assert result["speed"] == 1.5

    @pytest.mark.asyncio
    async def test_get_user_setting_default(self, database: Database, mock_asyncpg_pool: MagicMock):
        """デフォルトのユーザー設定"""
        database.pool = mock_asyncpg_pool

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_asyncpg_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_asyncpg_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await database.get_user_setting(999)

        assert result["speaker"] == 1
        assert result["speed"] == 1.0
        assert result["pitch"] == 0.0

    # ========================================
    # 辞書テスト
    # ========================================
    @pytest.mark.asyncio
    async def test_get_dict_from_cache(self, database: Database):
        """キャッシュから辞書を取得"""
        dict_data = {"hello": "ハロー"}
        database.cache.set_dict(123, dict_data)

        result = await database.get_dict(123)

        assert result == dict_data

    @pytest.mark.asyncio
    async def test_get_dict_zero_id(self, database: Database):
        """guild_id が 0 の場合は空辞書を返す"""
        result = await database.get_dict(0)

        assert result == {}

    @pytest.mark.asyncio
    async def test_load_guild_dict(self, database: Database, mock_asyncpg_pool: MagicMock):
        """VC接続時の辞書ロード"""
        database.pool = mock_asyncpg_pool

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "dict": json.dumps({"test": "テスト"})
        })
        mock_asyncpg_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_asyncpg_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await database.load_guild_dict(123)

        assert database.cache.is_guild_active(123) is True
        assert database.cache.is_dict_loaded(123) is True

    def test_unload_guild_dict(self, database: Database):
        """VC切断時の辞書アンロード"""
        database.cache.add_active_guild(123)
        database.cache.set_dict(123, {"test": "テスト"})

        database.unload_guild_dict(123)

        assert database.cache.is_guild_active(123) is False
        assert database.cache.get_dict(123) is None

    # ========================================
    # ブーストテスト
    # ========================================
    @pytest.mark.asyncio
    async def test_get_guild_boost_count_from_cache(self, database: Database):
        """キャッシュからブーストカウントを取得"""
        database.cache.set_boost_count(123, 3)

        result = await database.get_guild_boost_count(123)

        assert result == 3

    @pytest.mark.asyncio
    async def test_is_guild_boosted_true(self, database: Database):
        """ブースト済みギルドの判定"""
        database.cache.set_boost_count(123, 2)

        result = await database.is_guild_boosted(123)

        assert result is True

    @pytest.mark.asyncio
    async def test_is_guild_boosted_false(self, database: Database):
        """未ブーストギルドの判定"""
        database.cache.set_boost_count(123, 0)

        result = await database.is_guild_boosted(123)

        assert result is False

    # ========================================
    # インスタンスアクティブ判定テスト
    # ========================================
    @pytest.mark.asyncio
    async def test_is_instance_active_main_bot(self, database: Database):
        """メインBot (MIN_BOOST_LEVEL=0) は常にアクティブ"""
        with patch.dict("os.environ", {"MIN_BOOST_LEVEL": "0"}):
            result = await database.is_instance_active(123)
            assert result is True

    @pytest.mark.asyncio
    async def test_is_instance_active_skip_premium_check(self, database: Database):
        """SKIP_PREMIUM_CHECK=true の場合は常にアクティブ"""
        with patch.dict("os.environ", {"SKIP_PREMIUM_CHECK": "true", "MIN_BOOST_LEVEL": "1"}):
            result = await database.is_instance_active(123)
            assert result is True

    @pytest.mark.asyncio
    async def test_is_instance_active_sub_bot_insufficient_boosts(self, database: Database):
        """サブBot でブースト不足の場合は非アクティブ"""
        database.cache.set_boost_count(123, 1)  # 1ブーストのみ

        with patch.dict("os.environ", {"MIN_BOOST_LEVEL": "1", "SKIP_PREMIUM_CHECK": "false"}):
            result = await database.is_instance_active(123)
            assert result is False  # 2ブースト必要

    @pytest.mark.asyncio
    async def test_is_instance_active_sub_bot_sufficient_boosts(self, database: Database):
        """サブBot でブースト十分の場合はアクティブ"""
        database.cache.set_boost_count(123, 2)  # 2ブースト

        with patch.dict("os.environ", {"MIN_BOOST_LEVEL": "1", "SKIP_PREMIUM_CHECK": "false"}):
            result = await database.is_instance_active(123)
            assert result is True

    # ========================================
    # NOTIFY ハンドラテスト
    # ========================================
    def test_handle_guild_settings_change_update(self, database: Database):
        """ギルド設定変更の NOTIFY ハンドリング"""
        data = {"auto_join": True, "max_chars": 200}
        database._handle_guild_settings_change("UPDATE", 123, data)

        result = database.cache.get_guild_settings(123)
        assert result is not None
        assert result.auto_join is True

    def test_handle_guild_settings_change_delete(self, database: Database):
        """ギルド設定削除の NOTIFY ハンドリング"""
        database.cache.set_guild_settings(123, GuildSettings())
        database._handle_guild_settings_change("DELETE", 123, None)

        assert database.cache.get_guild_settings(123) is None

    def test_handle_user_settings_change(self, database: Database):
        """ユーザー設定変更の NOTIFY ハンドリング"""
        data = {"speaker": 3, "speed": 1.5, "pitch": 0.2}
        database._handle_user_settings_change("UPDATE", 456, data)

        result = database.cache.get_user_setting(456)
        assert result["speaker"] == 3

    def test_handle_boost_change_insert(self, database: Database):
        """ブースト追加の NOTIFY ハンドリング"""
        database.cache.set_boost_count(123, 1)
        database._handle_boost_change("INSERT", 123)

        assert database.cache.get_boost_count(123) == 2

    def test_handle_boost_change_delete(self, database: Database):
        """ブースト削除の NOTIFY ハンドリング"""
        database.cache.set_boost_count(123, 3)
        database._handle_boost_change("DELETE", 123)

        assert database.cache.get_boost_count(123) == 2

    # ========================================
    # 辞書 NOTIFY ハンドリングテスト
    # ========================================
    @pytest.mark.asyncio
    async def test_handle_dict_change_active_guild(self, database: Database):
        """アクティブギルドの辞書変更"""
        database.cache.add_active_guild(123)
        database.cache.set_dict(123, {"old": "オールド"})

        await database._handle_dict_change("UPDATE", 123)

        # 再ロードフラグがセットされる
        assert 123 in database.cache.pending_dict_reload

    @pytest.mark.asyncio
    async def test_handle_dict_change_inactive_guild(self, database: Database):
        """非アクティブギルドの辞書変更は無視"""
        database.cache.set_dict(123, {"old": "オールド"})

        await database._handle_dict_change("UPDATE", 123)

        # アクティブでないので何も起きない
        assert 123 not in database.cache.pending_dict_reload

    @pytest.mark.asyncio
    async def test_handle_dict_change_global_dict(self, database: Database, mock_asyncpg_pool: MagicMock):
        """グローバル辞書の変更は即座に再ロード"""
        database.pool = mock_asyncpg_pool
        database.cache.global_dict_id = 1201

        mock_conn = AsyncMock()
        mock_conn.fetchrow = AsyncMock(return_value={
            "dict": json.dumps({"global": "グローバル"})
        })
        mock_asyncpg_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_asyncpg_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=None)

        await database._handle_dict_change("UPDATE", 1201)

        # グローバル辞書は即座に再ロードされる
        result = database.cache.get_dict(1201)
        assert result is not None

    # ========================================
    # クローズテスト
    # ========================================
    @pytest.mark.asyncio
    async def test_close(self, database: Database, mock_asyncpg_pool: MagicMock, mock_asyncpg_connection: AsyncMock):
        """データベース接続のクローズ"""
        database.pool = mock_asyncpg_pool
        database._listener_connection = mock_asyncpg_connection
        database._listener_task = AsyncMock()
        database._listener_task.cancel = MagicMock()

        await database.close()

        assert database._shutdown is True
        mock_asyncpg_pool.close.assert_called_once()
