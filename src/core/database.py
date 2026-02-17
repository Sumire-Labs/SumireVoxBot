import json

import asyncpg
import os
from loguru import logger
from src.core.models import GuildSettings
from src.queries import UserSettingsQueries, DictQueries, GuildSettingsQueries, BillingQueries
from async_lru import alru_cache


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

            # 課金関連
            await conn.execute(BillingQueries.CREATE_USERS_TABLE)
            await conn.execute(BillingQueries.CREATE_BOOSTS_TABLE)
            await conn.execute(BillingQueries.CREATE_BOOSTS_GUILD_INDEX)
            await conn.execute(BillingQueries.CREATE_BOOSTS_USER_INDEX)

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

    # 課金・ブースト関連
    async def get_bot_instances(self) -> list[dict]:
        """アクティブなBotインスタンス一覧をDBから取得"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, client_id, bot_name, is_active FROM bot_instances WHERE is_active = true ORDER BY id ASC"
            )
            return [dict(r) for r in rows]

    async def get_user_slots_status(self, user_id: int) -> dict:
        """ユーザーのスロット数と使用済みスロット数を取得"""
        row = await self.pool.fetchrow(BillingQueries.GET_USER_SLOTS_STATUS, str(user_id))
        if row:
            return {"total": row["total_slots"], "used": row["used_slots"]}
        return {"total": 0, "used": 0}

    @alru_cache(maxsize=128, ttl=10)
    async def get_guild_boost_count(self, guild_id: int) -> int:
        """ギルドの合計ブースト数を取得（キャッシュ付き）"""
        count = await self.pool.fetchval(BillingQueries.GET_GUILD_BOOST_COUNT, int(guild_id))
        logger.debug(f"[DB DEBUG] get_guild_boost_count(guild_id={guild_id}, type={type(guild_id)}) -> count={count}")
        return count

    async def is_guild_boosted(self, guild_id: int) -> bool:
        """ギルドがブーストされているか確認（キャッシュ付き）"""
        return await self.get_guild_boost_count(int(guild_id)) > 0

    async def is_instance_active(self, guild_id: int) -> bool:
        """現在のインスタンスがこのサーバーでアクティブになるべきか判定"""
        min_level = int(os.getenv("MIN_BOOST_LEVEL", "0"))
        if min_level == 0:
            return True
        
        boost_count = await self.bot.db.get_guild_boost_count(int(guild_id))
        # 修正: LEVEL 1 (2台目) は 2ブースト以上でアクティブ
        # つまり boost_count >= (min_level + 1)
        return boost_count >= (min_level + 1)

    async def get_guild_booster(self, guild_id: int) -> str | None:
        """ギルドをブーストしているユーザーのIDを取得"""
        return await self.pool.fetchval(BillingQueries.GET_GUILD_BOOST_USER, int(guild_id))

    async def activate_guild_boost(self, guild_id: int, user_id: int) -> bool:
        """ギルドにブーストを適用する"""
        # すでにブーストされているか確認
        if await self.is_guild_boosted(int(guild_id)):
            return False
        
        # スロットに空きがあるか確認
        status = await self.get_user_slots_status(user_id)
        if status["total"] <= status["used"]:
            return False

        async with self.pool.acquire() as conn:
            await conn.execute(BillingQueries.INSERT_BOOST, int(guild_id), str(user_id))
        
        self.get_guild_boost_count.cache_clear()
        self.is_guild_boosted.cache_clear()
        logger.info(f"User {user_id} boosted guild {guild_id}")
        return True

    async def deactivate_guild_boost(self, guild_id: int, user_id: int) -> bool:
        """ギルドのブーストを解除する。1つだけ削除するようにCTIDを使用"""
        guild_id_int = int(guild_id)
        user_id_str = str(user_id)
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # 1件分のCTIDを取得
                row = await conn.fetchrow(
                    "SELECT ctid FROM guild_boosts WHERE guild_id = $1::BIGINT AND user_id = $2 LIMIT 1 FOR UPDATE",
                    guild_id_int,
                    user_id_str
                )
                if not row:
                    logger.info(f"Unboost attempt: No boost found for user {user_id_str} in guild {guild_id_int}")
                    return False
                
                # CTIDで削除
                status = await conn.execute(
                    "DELETE FROM guild_boosts WHERE ctid = $1",
                    row["ctid"]
                )
                
                # asyncpgのexecuteは "DELETE 1" のような文字列を返す
                success = status == "DELETE 1"
                
                if success:
                    self.get_guild_boost_count.cache_clear()
                    self.is_guild_boosted.cache_clear()
                    logger.info(f"User {user_id_str} removed one boost from guild {guild_id_int} (Status: {status})")
                else:
                    logger.warning(f"Failed to delete boost row with ctid {row['ctid']} for user {user_id_str} (Status: {status})")
                
                return success

    async def delete_guild_boosts_by_guild(self, guild_id: int):
        """ギルドの全ブーストを削除（Bot退出時用）"""
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM guild_boosts WHERE guild_id = $1::BIGINT", int(guild_id))
            self.get_guild_boost_count.cache_clear()
            self.is_guild_boosted.cache_clear()
            logger.info(f"Cleared all boosts for guild {guild_id} due to bot leave/kick")

    async def close(self):
        if self.pool:
            await self.pool.close()