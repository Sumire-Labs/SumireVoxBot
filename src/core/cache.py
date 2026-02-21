# src/core/cache.py

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
        self.global_dict_id: int = 0

        # 現在VC接続中のギルドID
        self.active_voice_guilds: Set[int] = set()

        # 辞書の再ロードが必要なギルド（NOTIFYでデータ省略時）
        self.pending_dict_reload: Set[int] = set()

        self._initialized = False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    # ========================================
    # ギルド設定
    # ========================================
    def get_guild_settings(self, guild_id: int) -> GuildSettings | None:
        return self.guild_settings.get(int(guild_id))

    def set_guild_settings(self, guild_id: int, settings: GuildSettings):
        self.guild_settings[int(guild_id)] = settings

    def invalidate_guild_settings(self, guild_id: int):
        self.guild_settings.pop(int(guild_id), None)

    # ========================================
    # ユーザー設定
    # ========================================
    def get_user_setting(self, user_id: int) -> dict | None:
        return self.user_settings.get(int(user_id))

    def set_user_setting(self, user_id: int, data: dict):
        self.user_settings[int(user_id)] = data

    def invalidate_user_setting(self, user_id: int):
        self.user_settings.pop(int(user_id), None)

    # ========================================
    # ブーストカウント
    # ========================================
    def get_boost_count(self, guild_id: int) -> int | None:
        return self.boost_counts.get(int(guild_id))

    def set_boost_count(self, guild_id: int, count: int):
        self.boost_counts[int(guild_id)] = count

    def increment_boost_count(self, guild_id: int):
        guild_id = int(guild_id)
        current = self.boost_counts.get(guild_id, 0)
        self.boost_counts[guild_id] = current + 1

    def decrement_boost_count(self, guild_id: int):
        guild_id = int(guild_id)
        current = self.boost_counts.get(guild_id, 0)
        self.boost_counts[guild_id] = max(0, current - 1)

    def invalidate_boost_count(self, guild_id: int):
        self.boost_counts.pop(int(guild_id), None)

    # ========================================
    # 辞書（動的ロード）
    # ========================================
    def get_dict(self, guild_id: int) -> dict | None:
        guild_id = int(guild_id)
        # 再ロードが必要なら None を返してキャッシュミスさせる
        if guild_id in self.pending_dict_reload:
            return None
        return self.dictionaries.get(guild_id)

    def set_dict(self, guild_id: int, data: dict):
        guild_id = int(guild_id)
        self.dictionaries[guild_id] = data
        # 再ロード完了したらフラグを解除
        self.pending_dict_reload.discard(guild_id)
        logger.debug(f"[Cache] Dictionary set: {guild_id} ({len(data)} entries)")

    def mark_dict_needs_reload(self, guild_id: int):
        """辞書の再ロードが必要であることをマーク"""
        guild_id = int(guild_id)
        if guild_id in self.dictionaries:
            self.pending_dict_reload.add(guild_id)
            logger.debug(f"[Cache] Dictionary marked for reload: {guild_id}")

    def remove_dict(self, guild_id: int):
        """辞書をRAMから削除（VC切断時）"""
        guild_id = int(guild_id)
        if guild_id in self.dictionaries and guild_id != self.global_dict_id:
            del self.dictionaries[guild_id]
            self.pending_dict_reload.discard(guild_id)
            logger.debug(f"[Cache] Dictionary unloaded: {guild_id}")

    def is_dict_loaded(self, guild_id: int) -> bool:
        guild_id = int(guild_id)
        return guild_id in self.dictionaries and guild_id not in self.pending_dict_reload

    # ========================================
    # VC接続状態管理
    # ========================================
    def add_active_guild(self, guild_id: int):
        self.active_voice_guilds.add(int(guild_id))
        logger.debug(f"[Cache] Guild marked as active: {guild_id}")

    def remove_active_guild(self, guild_id: int):
        self.active_voice_guilds.discard(int(guild_id))
        logger.debug(f"[Cache] Guild marked as inactive: {guild_id}")

    def is_guild_active(self, guild_id: int) -> bool:
        return int(guild_id) in self.active_voice_guilds

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
            "pending_dict_reload": len(self.pending_dict_reload),
        }
