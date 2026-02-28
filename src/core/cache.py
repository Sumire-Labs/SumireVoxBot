# src/core/cache.py

import asyncio
import time
from dataclasses import dataclass, field
from typing import Dict, Set, Optional, Generic, TypeVar
from loguru import logger
from src.core.models import GuildSettings

T = TypeVar('T')


@dataclass
class CacheEntry(Generic[T]):
    """TTL付きキャッシュエントリ"""
    value: T
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)

    def is_expired(self, ttl_seconds: float) -> bool:
        return time.time() - self.created_at > ttl_seconds

    def touch(self):
        """アクセス時刻を更新"""
        self.last_accessed = time.time()


class LRUCache(Generic[T]):
    """TTL + LRU キャッシュ"""

    def __init__(self, max_size: int = 10000, ttl_seconds: float = 3600):
        self._data: Dict[int, CacheEntry[T]] = {}
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: int) -> Optional[T]:
        async with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            if entry.is_expired(self._ttl_seconds):
                del self._data[key]
                return None
            entry.touch()
            return entry.value

    def get_sync(self, key: int) -> Optional[T]:
        """同期版get（ロックなし、読み取り専用の場合に使用）"""
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.is_expired(self._ttl_seconds):
            return None
        entry.touch()
        return entry.value

    async def set(self, key: int, value: T):
        async with self._lock:
            self._data[key] = CacheEntry(value=value)
            await self._evict_if_needed()

    def set_sync(self, key: int, value: T):
        """同期版set（初期ロード時に使用）"""
        self._data[key] = CacheEntry(value=value)

    async def delete(self, key: int) -> bool:
        async with self._lock:
            if key in self._data:
                del self._data[key]
                return True
            return False

    def delete_sync(self, key: int) -> bool:
        """同期版delete"""
        if key in self._data:
            del self._data[key]
            return True
        return False

    async def _evict_if_needed(self):
        """LRU方式で古いエントリを削除"""
        if len(self._data) <= self._max_size:
            return

        # 期限切れを先に削除
        now = time.time()
        expired_keys = [
            k for k, v in self._data.items()
            if v.is_expired(self._ttl_seconds)
        ]
        for key in expired_keys:
            del self._data[key]

        # まだオーバーしていればLRUで削除
        if len(self._data) > self._max_size:
            sorted_items = sorted(
                self._data.items(),
                key=lambda x: x[1].last_accessed
            )
            items_to_remove = len(self._data) - self._max_size
            for key, _ in sorted_items[:items_to_remove]:
                del self._data[key]

    async def clear(self):
        async with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def keys(self) -> set:
        return set(self._data.keys())


class SettingsCache:
    """インメモリキャッシュマネージャー（改善版）"""

    # キャッシュ設定
    GUILD_SETTINGS_TTL = 3600  # 1時間
    USER_SETTINGS_TTL = 3600  # 1時間
    BOOST_COUNT_TTL = 1800  # 30分
    DICT_TTL = 7200  # 2時間

    MAX_GUILD_SETTINGS = 50000
    MAX_USER_SETTINGS = 100000
    MAX_BOOST_COUNTS = 50000
    MAX_DICTIONARIES = 1000  # 辞書は大きいので少なめ

    def __init__(self):
        # LRU + TTL キャッシュ
        self.guild_settings: LRUCache[GuildSettings] = LRUCache(
            max_size=self.MAX_GUILD_SETTINGS,
            ttl_seconds=self.GUILD_SETTINGS_TTL
        )
        self.user_settings: LRUCache[dict] = LRUCache(
            max_size=self.MAX_USER_SETTINGS,
            ttl_seconds=self.USER_SETTINGS_TTL
        )
        self.boost_counts: LRUCache[int] = LRUCache(
            max_size=self.MAX_BOOST_COUNTS,
            ttl_seconds=self.BOOST_COUNT_TTL
        )
        self.dictionaries: LRUCache[dict] = LRUCache(
            max_size=self.MAX_DICTIONARIES,
            ttl_seconds=self.DICT_TTL
        )

        # グローバル辞書（別管理、TTLなし）
        self._global_dict: Optional[dict] = None
        self._global_dict_id: int = 0
        self._global_dict_lock = asyncio.Lock()

        # 現在VC接続中のギルドID
        self._active_voice_guilds: Set[int] = set()
        self._active_guilds_lock = asyncio.Lock()

        # 初期化フラグ
        self._initialized = False

        # キャッシュバージョン（NOTIFY切断からの復帰時にインクリメント）
        self._cache_version = 0

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def global_dict_id(self) -> int:
        return self._global_dict_id

    @global_dict_id.setter
    def global_dict_id(self, value: int):
        self._global_dict_id = value

    @property
    def cache_version(self) -> int:
        return self._cache_version

    def increment_cache_version(self):
        """キャッシュバージョンをインクリメント（再同期時に使用）"""
        self._cache_version += 1
        logger.info(f"Cache version incremented to {self._cache_version}")

    # ========================================
    # ギルド設定
    # ========================================
    async def get_guild_settings(self, guild_id: int) -> Optional[GuildSettings]:
        return await self.guild_settings.get(int(guild_id))

    def get_guild_settings_sync(self, guild_id: int) -> Optional[GuildSettings]:
        return self.guild_settings.get_sync(int(guild_id))

    async def set_guild_settings(self, guild_id: int, settings: GuildSettings):
        await self.guild_settings.set(int(guild_id), settings)

    def set_guild_settings_sync(self, guild_id: int, settings: GuildSettings):
        self.guild_settings.set_sync(int(guild_id), settings)

    async def invalidate_guild_settings(self, guild_id: int):
        await self.guild_settings.delete(int(guild_id))

    # ========================================
    # ユーザー設定
    # ========================================
    async def get_user_setting(self, user_id: int) -> Optional[dict]:
        return await self.user_settings.get(int(user_id))

    def get_user_setting_sync(self, user_id: int) -> Optional[dict]:
        return self.user_settings.get_sync(int(user_id))

    async def set_user_setting(self, user_id: int, data: dict):
        await self.user_settings.set(int(user_id), data)

    def set_user_setting_sync(self, user_id: int, data: dict):
        self.user_settings.set_sync(int(user_id), data)

    async def invalidate_user_setting(self, user_id: int):
        await self.user_settings.delete(int(user_id))

    # ========================================
    # ブーストカウント
    # ========================================
    async def get_boost_count(self, guild_id: int) -> Optional[int]:
        return await self.boost_counts.get(int(guild_id))

    def get_boost_count_sync(self, guild_id: int) -> Optional[int]:
        return self.boost_counts.get_sync(int(guild_id))

    async def set_boost_count(self, guild_id: int, count: int):
        await self.boost_counts.set(int(guild_id), count)

    def set_boost_count_sync(self, guild_id: int, count: int):
        self.boost_counts.set_sync(int(guild_id), count)

    async def invalidate_boost_count(self, guild_id: int):
        """ブーストカウントを無効化（次回アクセス時にDBから再取得）"""
        await self.boost_counts.delete(int(guild_id))

    # ========================================
    # 辞書（動的ロード）
    # ========================================
    async def get_dict(self, guild_id: int) -> Optional[dict]:
        guild_id = int(guild_id)

        # グローバル辞書
        if guild_id == self._global_dict_id:
            async with self._global_dict_lock:
                return self._global_dict

        return await self.dictionaries.get(guild_id)

    def get_dict_sync(self, guild_id: int) -> Optional[dict]:
        guild_id = int(guild_id)
        if guild_id == self._global_dict_id:
            return self._global_dict
        return self.dictionaries.get_sync(guild_id)

    async def set_dict(self, guild_id: int, data: dict):
        guild_id = int(guild_id)

        # グローバル辞書
        if guild_id == self._global_dict_id:
            async with self._global_dict_lock:
                self._global_dict = data
                logger.debug(f"[Cache] Global dictionary set ({len(data)} entries)")
            return

        await self.dictionaries.set(guild_id, data)
        logger.debug(f"[Cache] Dictionary set: {guild_id} ({len(data)} entries)")

    def set_dict_sync(self, guild_id: int, data: dict):
        guild_id = int(guild_id)
        if guild_id == self._global_dict_id:
            self._global_dict = data
            logger.debug(f"[Cache] Global dictionary set ({len(data)} entries)")
            return
        self.dictionaries.set_sync(guild_id, data)
        logger.debug(f"[Cache] Dictionary set: {guild_id} ({len(data)} entries)")

    async def invalidate_dict(self, guild_id: int):
        """辞書を無効化（即座に削除）"""
        guild_id = int(guild_id)

        if guild_id == self._global_dict_id:
            async with self._global_dict_lock:
                self._global_dict = None
            logger.debug(f"[Cache] Global dictionary invalidated")
            return

        await self.dictionaries.delete(guild_id)
        logger.debug(f"[Cache] Dictionary invalidated: {guild_id}")

    async def remove_dict(self, guild_id: int):
        """辞書をRAMから削除（VC切断時）"""
        guild_id = int(guild_id)

        # グローバル辞書は削除しない
        if guild_id == self._global_dict_id:
            return

        deleted = await self.dictionaries.delete(guild_id)
        if deleted:
            logger.debug(f"[Cache] Dictionary unloaded: {guild_id}")

    def is_dict_loaded(self, guild_id: int) -> bool:
        guild_id = int(guild_id)
        if guild_id == self._global_dict_id:
            return self._global_dict is not None
        return self.dictionaries.get_sync(guild_id) is not None

    # ========================================
    # VC接続状態管理
    # ========================================
    async def add_active_guild(self, guild_id: int):
        async with self._active_guilds_lock:
            self._active_voice_guilds.add(int(guild_id))
        logger.debug(f"[Cache] Guild marked as active: {guild_id}")

    async def remove_active_guild(self, guild_id: int):
        async with self._active_guilds_lock:
            self._active_voice_guilds.discard(int(guild_id))
        logger.debug(f"[Cache] Guild marked as inactive: {guild_id}")

    def is_guild_active(self, guild_id: int) -> bool:
        return int(guild_id) in self._active_voice_guilds

    def get_active_guilds(self) -> Set[int]:
        return self._active_voice_guilds.copy()

    # ========================================
    # 初期化・統計
    # ========================================
    def mark_initialized(self):
        self._initialized = True

    def stats(self) -> dict:
        return {
            "guild_settings": len(self.guild_settings),
            "user_settings": len(self.user_settings),
            "boost_counts": len(self.boost_counts),
            "dictionaries_loaded": len(self.dictionaries),
            "global_dict_loaded": self._global_dict is not None,
            "active_voice_guilds": len(self._active_voice_guilds),
            "cache_version": self._cache_version,
        }

    async def clear_all(self):
        """全キャッシュをクリア"""
        await self.guild_settings.clear()
        await self.user_settings.clear()
        await self.boost_counts.clear()
        await self.dictionaries.clear()
        async with self._global_dict_lock:
            self._global_dict = None
        async with self._active_guilds_lock:
            self._active_voice_guilds.clear()
        self._initialized = False
        logger.info("[Cache] All caches cleared")
