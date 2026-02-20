# src/core/database.py

import json
import asyncio
import asyncpg
import os
from loguru import logger
from src.core.models import GuildSettings
from src.core.cache import SettingsCache
from src.queries import UserSettingsQueries, DictQueries, GuildSettingsQueries, BillingQueries


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None
        self.cache = SettingsCache()
        self._listener_connection: asyncpg.Connection | None = None
        self._listener_task: asyncio.Task | None = None

    async def connect(self):
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                database=os.getenv("POSTGRES_DB"),
                host=os.getenv("POSTGRES_HOST"),
                port=os.getenv("POSTGRES_PORT"),
                min_size=2,
                max_size=10
            )

    async def init_db(self):
        if self.pool is None:
            await self.connect()

        async with self.pool.acquire() as conn:
            # テーブル作成
            await conn.execute(UserSettingsQueries.CREATE_TABLE)
            await conn.execute(DictQueries.CREATE_TABLE)
            await conn.execute(GuildSettingsQueries.CREATE_TABLE)
            await conn.execute(BillingQueries.CREATE_USERS_TABLE)
            await conn.execute(BillingQueries.CREATE_BOOSTS_TABLE)
            await conn.execute(BillingQueries.CREATE_BOOSTS_GUILD_INDEX)
            await conn.execute(BillingQueries.CREATE_BOOSTS_USER_INDEX)

            # トリガー作成
            await self._setup_triggers(conn)

        # グローバル辞書IDを設定
        self.cache.global_dict_id = int(os.getenv("GLOBAL_DICT_ID", "0"))

        # 起動時データロード
        await self._load_initial_data()

        # LISTEN開始
        await self._start_listener()

    async def _setup_triggers(self, conn: asyncpg.Connection):
        """通知トリガーをセットアップ"""
        trigger_sql = """
                      -- 通知用の関数（INSERT/UPDATE）
                      CREATE OR REPLACE FUNCTION notify_settings_change()
                          RETURNS TRIGGER AS \
                      $$
                      DECLARE
                          record_id   BIGINT;
                          record_data JSONB;
                      BEGIN
                          CASE TG_TABLE_NAME
                              WHEN 'guild_settings' THEN record_id := NEW.guild_id; \
                                                         record_data := NEW.settings;
                              WHEN 'dict' THEN record_id := NEW.guild_id; \
                                               record_data := NEW.dict;
                              WHEN 'user_settings' THEN record_id := NEW.user_id; \
                                                        record_data := json_build_object( \
                                                                'speaker', NEW.speaker, \
                                                                'speed', NEW.speed, \
                                                                'pitch', NEW.pitch \
                                                                       );
                              WHEN 'guild_boosts' THEN record_id := NEW.guild_id; \
                                                       record_data := NULL;
                              ELSE record_id := NULL; \
                                   record_data := NULL;
                              END CASE;

                          PERFORM pg_notify(
                                  'settings_change',
                                  json_build_object(
                                          'table', TG_TABLE_NAME,
                                          'operation', TG_OP,
                                          'id', record_id,
                                          'data', record_data
                                  )::text
                                  );
                          RETURN NEW;
                      END;

                      $$ LANGUAGE plpgsql;

                      -- 通知用の関数（DELETE）
                      CREATE OR REPLACE FUNCTION notify_settings_delete()
                          RETURNS TRIGGER AS \
                      $$
                      DECLARE
                          record_id BIGINT;
                      BEGIN
                          CASE TG_TABLE_NAME
                              WHEN 'guild_settings' THEN record_id := OLD.guild_id;
                              WHEN 'dict' THEN record_id := OLD.guild_id;
                              WHEN 'user_settings' THEN record_id := OLD.user_id;
                              WHEN 'guild_boosts' THEN record_id := OLD.guild_id;
                              ELSE record_id := NULL;
                              END CASE;

                          PERFORM pg_notify(
                                  'settings_change',
                                  json_build_object(
                                          'table', TG_TABLE_NAME,
                                          'operation', 'DELETE',
                                          'id', record_id
                                  )::text
                                  );
                          RETURN OLD;
                      END;

                      $$ LANGUAGE plpgsql;

                      -- guild_settings トリガー
                      DROP TRIGGER IF EXISTS guild_settings_notify ON guild_settings;
                      CREATE TRIGGER guild_settings_notify
                          AFTER INSERT OR UPDATE \
                          ON guild_settings
                          FOR EACH ROW \
                      EXECUTE FUNCTION notify_settings_change();

                      DROP TRIGGER IF EXISTS guild_settings_delete_notify ON guild_settings;
                      CREATE TRIGGER guild_settings_delete_notify
                          AFTER DELETE \
                          ON guild_settings
                          FOR EACH ROW \
                      EXECUTE FUNCTION notify_settings_delete();

                      -- dict トリガー
                      DROP TRIGGER IF EXISTS dict_notify ON dict;
                      CREATE TRIGGER dict_notify
                          AFTER INSERT OR UPDATE \
                          ON dict
                          FOR EACH ROW \
                      EXECUTE FUNCTION notify_settings_change();

                      DROP TRIGGER IF EXISTS dict_delete_notify ON dict;
                      CREATE TRIGGER dict_delete_notify
                          AFTER DELETE \
                          ON dict
                          FOR EACH ROW \
                      EXECUTE FUNCTION notify_settings_delete();

                      -- user_settings トリガー
                      DROP TRIGGER IF EXISTS user_settings_notify ON user_settings;
                      CREATE TRIGGER user_settings_notify
                          AFTER INSERT OR UPDATE \
                          ON user_settings
                          FOR EACH ROW \
                      EXECUTE FUNCTION notify_settings_change();

                      DROP TRIGGER IF EXISTS user_settings_delete_notify ON user_settings;
                      CREATE TRIGGER user_settings_delete_notify
                          AFTER DELETE \
                          ON user_settings
                          FOR EACH ROW \
                      EXECUTE FUNCTION notify_settings_delete();

                      -- guild_boosts トリガー
                      DROP TRIGGER IF EXISTS guild_boosts_notify ON guild_boosts;
                      CREATE TRIGGER guild_boosts_notify
                          AFTER INSERT \
                          ON guild_boosts
                          FOR EACH ROW \
                      EXECUTE FUNCTION notify_settings_change();

                      DROP TRIGGER IF EXISTS guild_boosts_delete_notify ON guild_boosts;
                      CREATE TRIGGER guild_boosts_delete_notify
                          AFTER DELETE \
                          ON guild_boosts
                          FOR EACH ROW \
                      EXECUTE FUNCTION notify_settings_delete(); \
                      """
        await conn.execute(trigger_sql)
        logger.info("Database triggers initialized")

    async def _load_initial_data(self):
        """起動時に必要なデータをキャッシュにロード"""
        logger.info("Loading initial data to cache...")

        async with self.pool.acquire() as conn:
            # ギルド設定（全件）
            rows = await conn.fetch("SELECT guild_id, settings FROM guild_settings")
            for row in rows:
                try:
                    raw_data = row['settings']
                    if isinstance(raw_data, str):
                        raw_data = json.loads(raw_data)
                    settings = GuildSettings.model_validate(raw_data)
                    self.cache.set_guild_settings(row['guild_id'], settings)
                except Exception as e:
                    logger.error(f"Failed to load guild settings {row['guild_id']}: {e}")

            # ユーザー設定（全件）
            rows = await conn.fetch("SELECT user_id, speaker, speed, pitch FROM user_settings")
            for row in rows:
                self.cache.set_user_setting(row['user_id'], {
                    "speaker": row['speaker'],
                    "speed": row['speed'],
                    "pitch": row['pitch']
                })

            # ブーストカウント（全件）
            rows = await conn.fetch(
                "SELECT guild_id, COUNT(*) as count FROM guild_boosts GROUP BY guild_id"
            )
            for row in rows:
                self.cache.set_boost_count(row['guild_id'], row['count'])

            # グローバル辞書のみロード
            if self.cache.global_dict_id:
                row = await conn.fetchrow(DictQueries.GET_DICT, self.cache.global_dict_id)
                if row:
                    raw_data = row['dict']
                    if isinstance(raw_data, str):
                        raw_data = json.loads(raw_data)
                    self.cache.set_dict(self.cache.global_dict_id, raw_data)
                    logger.info(f"Global dictionary loaded: {len(raw_data)} entries")

        self.cache._initialized = True
        stats = self.cache.stats()
        logger.success(
            f"Cache initialized: {stats['guild_settings']} guilds, "
            f"{stats['user_settings']} users, {stats['boost_counts']} boost records"
        )

    # ========================================
    # LISTEN/NOTIFY
    # ========================================
    async def _start_listener(self):
        """LISTEN/NOTIFY のリスナーを開始"""
        self._listener_connection = await asyncpg.connect(
            user=os.getenv("POSTGRES_USER"),
            password=os.getenv("POSTGRES_PASSWORD"),
            database=os.getenv("POSTGRES_DB"),
            host=os.getenv("POSTGRES_HOST"),
            port=os.getenv("POSTGRES_PORT")
        )

        await self._listener_connection.add_listener('settings_change', self._on_notification)
        logger.info("Started listening for database notifications")

        self._listener_task = asyncio.create_task(self._keep_listener_alive())

    async def _keep_listener_alive(self):
        """リスナー接続を維持"""
        while True:
            try:
                await asyncio.sleep(30)
                if self._listener_connection.is_closed():
                    logger.warning("Listener connection lost, reconnecting...")
                    await self._start_listener()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Listener keep-alive error: {e}")

    def _on_notification(self, connection, pid, channel, payload):
        """通知を受け取った時のコールバック"""
        try:
            data = json.loads(payload)
            table = data.get('table')
            operation = data.get('operation')
            record_id = data.get('id')
            record_data = data.get('data')

            logger.debug(f"[NOTIFY] {operation} on {table}, id={record_id}")

            if table == 'guild_settings':
                self._handle_guild_settings_change(operation, record_id, record_data)
            elif table == 'dict':
                self._handle_dict_change(operation, record_id, record_data)
            elif table == 'user_settings':
                self._handle_user_settings_change(operation, record_id, record_data)
            elif table == 'guild_boosts':
                self._handle_boost_change(operation, record_id)

        except Exception as e:
            logger.error(f"Failed to process notification: {e}")

    def _handle_guild_settings_change(self, operation: str, guild_id: int, data):
        if operation == 'DELETE':
            self.cache.invalidate_guild_settings(guild_id)
        else:
            try:
                if isinstance(data, str):
                    data = json.loads(data)
                settings = GuildSettings.model_validate(data)
                self.cache.set_guild_settings(guild_id, settings)
                logger.debug(f"[Cache] Guild settings updated via NOTIFY: {guild_id}")
            except Exception as e:
                logger.error(f"Failed to update guild settings cache: {e}")
                self.cache.invalidate_guild_settings(guild_id)

    def _handle_dict_change(self, operation: str, guild_id: int, data):
        # グローバル辞書は常に更新
        if guild_id == self.cache.global_dict_id:
            if operation == 'DELETE':
                self.cache.set_dict(guild_id, {})
            else:
                try:
                    if isinstance(data, str):
                        data = json.loads(data)
                    self.cache.set_dict(guild_id, data)
                    logger.debug(f"[Cache] Global dictionary updated via NOTIFY")
                except Exception as e:
                    logger.error(f"Failed to update global dict cache: {e}")
            return

        # 通常の辞書はVC接続中のギルドのみ更新
        if self.cache.is_guild_active(guild_id):
            if operation == 'DELETE':
                self.cache.set_dict(guild_id, {})
            else:
                try:
                    if isinstance(data, str):
                        data = json.loads(data)
                    self.cache.set_dict(guild_id, data)
                    logger.debug(f"[Cache] Dictionary updated via NOTIFY: {guild_id}")
                except Exception as e:
                    logger.error(f"Failed to update dict cache: {e}")

    def _handle_user_settings_change(self, operation: str, user_id: int, data):
        if operation == 'DELETE':
            self.cache.invalidate_user_setting(user_id)
        else:
            try:
                if isinstance(data, str):
                    data = json.loads(data)
                self.cache.set_user_setting(user_id, data)
                logger.debug(f"[Cache] User settings updated via NOTIFY: {user_id}")
            except Exception as e:
                logger.error(f"Failed to update user settings cache: {e}")
                self.cache.invalidate_user_setting(user_id)

    def _handle_boost_change(self, operation: str, guild_id: int):
        if operation == 'DELETE':
            self.cache.decrement_boost_count(guild_id)
        elif operation == 'INSERT':
            self.cache.increment_boost_count(guild_id)
        logger.debug(f"[Cache] Boost count updated via NOTIFY: {guild_id}")

    # ========================================
    # 辞書の動的ロード/アンロード
    # ========================================
    async def load_guild_dict(self, guild_id: int):
        """VC接続時に辞書をロード"""
        self.cache.add_active_guild(guild_id)

        # 既にロード済みならスキップ
        if self.cache.is_dict_loaded(guild_id):
            return

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(DictQueries.GET_DICT, guild_id)
            if row:
                raw_data = row['dict']
                if isinstance(raw_data, str):
                    raw_data = json.loads(raw_data)
                self.cache.set_dict(guild_id, raw_data)
            else:
                self.cache.set_dict(guild_id, {})

        logger.info(f"[{guild_id}] Dictionary loaded for voice session")

    def unload_guild_dict(self, guild_id: int):
        """VC切断時に辞書をアンロード"""
        self.cache.remove_active_guild(guild_id)
        self.cache.remove_dict(guild_id)
        logger.info(f"[{guild_id}] Dictionary unloaded after voice session")

    # ========================================
    # 公開API（キャッシュ優先）
    # ========================================
    async def get_guild_settings(self, guild_id: int) -> GuildSettings:
        """ギルド設定を取得"""
        cached = self.cache.get_guild_settings(guild_id)
        if cached is not None:
            return cached

        # キャッシュミス時はDBから取得
        row = await self.pool.fetchrow(GuildSettingsQueries.GET_SETTINGS, guild_id)
        if row:
            raw_data = row['settings']
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)
            settings = GuildSettings.model_validate(raw_data)
            self.cache.set_guild_settings(guild_id, settings)
            return settings

        return GuildSettings()

    async def set_guild_settings(self, guild_id: int, settings: GuildSettings):
        """ギルド設定を保存"""
        settings_dict = settings.model_dump()
        settings_json = json.dumps(settings_dict)
        await self.pool.execute(GuildSettingsQueries.SET_SETTINGS, guild_id, settings_json)
        # NOTIFYトリガーによりキャッシュは自動更新

    async def get_user_setting(self, user_id: int) -> dict:
        """ユーザー設定を取得"""
        cached = self.cache.get_user_setting(user_id)
        if cached is not None:
            return cached

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(UserSettingsQueries.GET_SETTINGS, user_id)
            if row:
                data = {"speaker": row['speaker'], "speed": row['speed'], "pitch": row['pitch']}
                self.cache.set_user_setting(user_id, data)
                return data

        return {"speaker": 1, "speed": 1.0, "pitch": 0.0}

    async def set_user_setting(self, user_id: int, speaker: int, speed: float, pitch: float):
        """ユーザー設定を保存"""
        async with self.pool.acquire() as conn:
            await conn.execute(UserSettingsQueries.SET_SETTINGS, user_id, speaker, speed, pitch)
        # NOTIFYトリガーによりキャッシュは自動更新

    async def get_dict(self, guild_id: int) -> dict:
        """辞書を取得"""
        cached = self.cache.get_dict(guild_id)
        if cached is not None:
            return cached

        # キャッシュミス（通常はVC接続時にロード済みのはず）
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(DictQueries.GET_DICT, guild_id)
            if row:
                raw_data = row['dict']
                if isinstance(raw_data, str):
                    raw_data = json.loads(raw_data)
                # VC接続中ならキャッシュに保存
                if self.cache.is_guild_active(guild_id) or guild_id == self.cache.global_dict_id:
                    self.cache.set_dict(guild_id, raw_data)
                return raw_data

        return {}

    async def add_or_update_dict(self, guild_id: int, dict_data: dict):
        """辞書を保存"""
        dict_json = json.dumps(dict_data)
        async with self.pool.acquire() as conn:
            await conn.execute(DictQueries.INSERT_DICT, guild_id, dict_json)
        # NOTIFYトリガーによりキャッシュは自動更新
        return True

    async def get_guild_boost_count(self, guild_id: int) -> int:
        """ブーストカウントを取得"""
        guild_id_int = int(guild_id)

        cached = self.cache.get_boost_count(guild_id_int)
        if cached is not None:
            return cached

        count = await self.pool.fetchval(BillingQueries.GET_GUILD_BOOST_COUNT, guild_id_int)
        count = count or 0
        self.cache.set_boost_count(guild_id_int, count)
        return count

    async def is_guild_boosted(self, guild_id: int) -> bool:
        """ブーストされているか確認"""
        return await self.get_guild_boost_count(int(guild_id)) > 0

    async def is_instance_active(self, guild_id: int) -> bool:
        """インスタンスがアクティブか判定"""
        if os.getenv("SKIP_PREMIUM_CHECK", "false").lower() == "true":
            return True

        min_level = int(os.getenv("MIN_BOOST_LEVEL", "0"))
        if min_level == 0:
            return True

        boost_count = await self.get_guild_boost_count(int(guild_id))
        return boost_count >= (min_level + 1)

    # ========================================
    # その他（既存のまま）
    # ========================================
    async def get_bot_instances(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, client_id, bot_name, is_active FROM bot_instances WHERE is_active = true ORDER BY id ASC"
            )
            return [dict(r) for r in rows]

    async def get_user_slots_status(self, user_id: int) -> dict:
        row = await self.pool.fetchrow(BillingQueries.GET_USER_SLOTS_STATUS, str(user_id))
        if row:
            return {"total": row["total_slots"], "used": row["used_slots"]}
        return {"total": 0, "used": 0}

    async def get_guild_booster(self, guild_id: int) -> str | None:
        return await self.pool.fetchval(BillingQueries.GET_GUILD_BOOST_USER, int(guild_id))

    async def activate_guild_boost(self, guild_id: int, user_id: int) -> bool:
        guild_id_int = int(guild_id)
        user_id_str = str(user_id)

        bot_instances = await self.get_bot_instances()
        max_boosts = len(bot_instances)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                user = await conn.fetchrow(
                    "SELECT total_slots FROM users WHERE discord_id = $1 FOR UPDATE",
                    user_id_str
                )
                if not user:
                    logger.warning(f"Activate boost failed: User {user_id_str} not found")
                    return False

                total_slots = user["total_slots"]
                used_slots = await conn.fetchval(
                    "SELECT COUNT(*) FROM guild_boosts WHERE user_id = $1",
                    user_id_str
                )

                if used_slots >= total_slots:
                    logger.warning(f"Activate boost failed: No empty slots ({used_slots}/{total_slots})")
                    return False

                current_guild_boosts = await conn.fetchval(
                    "SELECT COUNT(*) FROM guild_boosts WHERE guild_id = $1::BIGINT",
                    guild_id_int
                )
                if current_guild_boosts >= max_boosts:
                    logger.warning(f"Activate boost failed: Guild at max boosts")
                    return False

                await conn.execute(
                    "INSERT INTO guild_boosts (guild_id, user_id) VALUES ($1::BIGINT, $2)",
                    guild_id_int,
                    user_id_str
                )
                logger.info(f"User {user_id_str} boosted guild {guild_id_int}")
                return True

    async def deactivate_guild_boost(self, guild_id: int, user_id: int) -> bool:
        guild_id_int = int(guild_id)
        user_id_str = str(user_id)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT ctid FROM guild_boosts WHERE guild_id = $1::BIGINT AND user_id = $2 LIMIT 1 FOR UPDATE",
                    guild_id_int,
                    user_id_str
                )
                if not row:
                    return False

                status = await conn.execute(
                    "DELETE FROM guild_boosts WHERE ctid = $1",
                    row["ctid"]
                )
                success = status == "DELETE 1"
                if success:
                    logger.info(f"User {user_id_str} unboosted guild {guild_id_int}")
                return success

    async def delete_guild_boosts_by_guild(self, guild_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM guild_boosts WHERE guild_id = $1::BIGINT", int(guild_id))
        logger.info(f"Cleared all boosts for guild {guild_id}")

    async def close(self):
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._listener_connection and not self._listener_connection.is_closed():
            await self._listener_connection.close()

        if self.pool:
            await self.pool.close()

        logger.info("Database connections closed")