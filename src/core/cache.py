# src/core/cache.py

import json
from loguru import logger
from src.core.models import GuildSettings
from typing import Dict, Set


class SettingsCache:
    """インメモリキャッシュマネージャー"""

    def __init__(self):
        # 起動時に全ロード
        self.guild_settings: Dict[int, GuildSettings] = {}
        self.user_settings: Dict[int, dict] = {}
        self.boost_counts: Dict[int, int] = {}

        # 動的ロード（VC接続中のみ）
        self.dictionaries: Dict[int, dict] = {}

        # グローバル辞書ID
        self.global_dict_id: int | None = None

        # 現在VC接続中のギルドID
        self.active_voice_guilds: Set[int] = set()

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ========================================
    # ギルド設定
    # ========================================
    def get_guild_settings(self, guild_id: int) -> GuildSettings | None:
        return self.guild_settings.get(guild_id)

    def set_guild_settings(self, guild_id: int, settings: GuildSettings):
        self.guild_settings[guild_id] = settings

    def invalidate_guild_settings(self, guild_id: int):
        self.guild_settings.pop(guild_id, None)

    # ========================================
    # ユーザー設定
    # ========================================
    def get_user_setting(self, user_id: int) -> dict | None:
        return self.user_settings.get(user_id)

    def set_user_setting(self, user_id: int, data: dict):
        self.user_settings[user_id] = data

    def invalidate_user_setting(self, user_id: int):
        self.user_settings.pop(user_id, None)

    # ========================================
    # ブーストカウント
    # ========================================
    def get_boost_count(self, guild_id: int) -> int | None:
        return self.boost_counts.get(guild_id)

    def set_boost_count(self, guild_id: int, count: int):
        self.boost_counts[guild_id] = count

    def increment_boost_count(self, guild_id: int):
        current = self.boost_counts.get(guild_id, 0)
        self.boost_counts[guild_id] = current + 1

    def decrement_boost_count(self, guild_id: int):
        current = self.boost_counts.get(guild_id, 0)
        self.boost_counts[guild_id] = max(0, current - 1)

    def invalidate_boost_count(self, guild_id: int):
        self.boost_counts.pop(guild_id, None)

    # ========================================
    # 辞書（動的ロード）
    # ========================================
    def get_dict(self, guild_id: int) -> dict | None:
        return self.dictionaries.get(guild_id)

    def set_dict(self, guild_id: int, data: dict):
        self.dictionaries[guild_id] = data
        logger.debug(f"[Cache] Dictionary loaded: {guild_id} ({len(data)} entries)")

    def remove_dict(self, guild_id: int):
        """辞書をRAMから削除（VC切断時）"""
        if guild_id in self.dictionaries and guild_id != self.global_dict_id:
            del self.dictionaries[guild_id]
            logger.debug(f"[Cache] Dictionary unloaded: {guild_id}")

    def is_dict_loaded(self, guild_id: int) -> bool:
        return guild_id in self.dictionaries

    # ========================================
    # VC接続状態管理
    # ========================================
    def add_active_guild(self, guild_id: int):
        self.active_voice_guilds.add(guild_id)
        logger.debug(f"[Cache] Guild marked as active: {guild_id}")

    def remove_active_guild(self, guild_id: int):
        self.active_voice_guilds.discard(guild_id)
        logger.debug(f"[Cache] Guild marked as inactive: {guild_id}")

    def is_guild_active(self, guild_id: int) -> bool:
        return guild_id in self.active_voice_guilds

    # ========================================
    # 統計
    # ========================================
    def stats(self) -> dict:
        return {
            "guild_settings": len(self.guild_settings),
            "user_settings": len(self.user_settings),
            "boost_counts": len(self.boost_counts),
            "dictionaries_loaded": len(self.dictionaries),
            "active_voice_guilds": len(self.active_voice_guilds),
        }
