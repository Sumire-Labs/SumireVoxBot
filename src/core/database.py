import json

import asyncpg
import os
from loguru import logger
from src.core.models import GuildSettings
from src.queries import UserSettingsQueries, DictQueries, GuildSettingsQueries


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                database=os.getenv("POSTGRES_DB"),
                host=os.getenv("POSTGRES_HOST"),
                port=os.getenv("POSTGRES_PORT")
            )

    async def init_db(self):
        if self.pool is None:
            await self.connect()

        async with self.pool.acquire() as conn:
            # ユーザー設定
            await conn.execute(UserSettingsQueries.CREATE_TABLE)
            # サーバーごとの辞書
            await conn.execute(DictQueries.CREATE_TABLE)
            # サーバーごとの設定
            await conn.execute(GuildSettingsQueries.CREATE_TABLE)

    async def get_guild_settings(self, guild_id: int) -> GuildSettings:
        """サーバー設定を取得する。型が文字列でも辞書でも対応できるようにする"""
        row = await self.pool.fetchrow(GuildSettingsQueries.GET_SETTINGS, guild_id)

        if row:
            raw_data = row['settings']

            # もしデータが文字列(str)で返ってきたら辞書に変換
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except json.JSONDecodeError:
                    logger.error(f"JSONのパースに失敗しました: {raw_data}")
                    return GuildSettings()

            # 辞書(dict)としてPydanticでバリデーション
            return GuildSettings.model_validate(raw_data)

        # データがない場合はデフォルト設定
        return GuildSettings()

    async def set_guild_settings(self, guild_id: int, settings: GuildSettings):
        """サーバー設定を保存する"""
        # Pydanticモデルを辞書に変換
        settings_dict = settings.model_dump()
        settings_json = json.dumps(settings_dict)

        # INSERT ... ON CONFLICT (UPSERT) で保存
        await self.pool.execute(GuildSettingsQueries.SET_SETTINGS, guild_id, settings_json)

        logger.debug(f"[{guild_id}] サーバー設定を更新しました。")

    # ユーザー設定の取得
    async def get_user_setting(self, user_id: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                UserSettingsQueries.GET_SETTINGS,
                user_id
            )
            if row:
                return {"speaker": row['speaker'], "speed": row['speed'], "pitch": row['pitch']}
            return {"speaker": 1, "speed": 1.0, "pitch": 0.0}

    # ユーザー設定の保存
    async def set_user_setting(self, user_id: int, speaker: int, speed: float, pitch: float):
        async with self.pool.acquire() as conn:
            await conn.execute(UserSettingsQueries.SET_SETTINGS, user_id, speaker, speed, pitch)

    async def get_dict(self, guild_id: int):
        """特定のギルドの辞書を辞書形式で取得"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(DictQueries.GET_DICT, guild_id)
            if row:
                raw_data = row['dict']

                # もしデータが文字列(str)で返ってきたら辞書に変換
                if isinstance(raw_data, str):
                    try:
                        return json.loads(raw_data)
                    except json.JSONDecodeError:
                        logger.error(f"辞書のJSONパースに失敗しました: {raw_data}")
                        return {}

                # 辞書(dict)として返す
                return raw_data
            return {}

    # ギルド辞書の登録または更新
    async def add_or_update_dict(self, guild_id: int, dict_data: dict):
        """ギルド辞書を登録または更新する"""
        dict_json = json.dumps(dict_data)
        async with self.pool.acquire() as conn:
            await conn.execute(DictQueries.INSERT_DICT, guild_id, dict_json)
        logger.debug(f"[{guild_id}] 辞書を更新しました。")
        return True

    async def close(self):
        if self.pool:
            await self.pool.close()