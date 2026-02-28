# src/core/database.py

import json
import asyncio
import asyncpg
import os
from loguru import logger
from src.core.models import GuildSettings
from src.core.cache import SettingsCache
from src.queries import UserSettingsQueries, DictQueries, GuildSettingsQueries, BillingQueries, VoiceSessionQueries


class Database:
    # リスナー再接続設定
    LISTENER_RECONNECT_DELAY = 5  # 秒
    LISTENER_HEALTH_CHECK_INTERVAL = 30  # 秒
    MAX_RECONNECT_ATTEMPTS = 10

    def __init__(self):
        self.pool: asyncpg.Pool | None = None
        self.cache = SettingsCache()
        self._listener_connection: asyncpg.Connection | None = None
        self._listener_task: asyncio.Task | None = None
        self._shutdown = False
        self._listener_healthy = False
        self._reconnect_attempts = 0
        self._last_notification_time: float = 0

        # 通知処理用のロック（同時処理による競合防止）
        self._notification_lock = asyncio.Lock()

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
            await conn.execute(VoiceSessionQueries.CREATE_TABLE)
            await conn.execute(VoiceSessionQueries.CREATE_BOT_INDEX)

            # トリガー作成
            await self._setup_triggers(conn)

        # グローバル辞書IDを設定
        self.cache.global_dict_id = int(os.getenv("GLOBAL_DICT_ID", "0"))

        # 起動時データロード
        await self._load_initial_data()

        # LISTEN開始
        await self._start_listener()

    async def _setup_triggers(self, conn: asyncpg.Connection):
        """通知トリガーをセットアップ（ブーストカウントは絶対値を送信）"""
        trigger_sql = """
                      -- 通知用の関数（INSERT/UPDATE）
                      CREATE OR REPLACE FUNCTION notify_settings_change()
                          RETURNS TRIGGER AS

                      $$
                      DECLARE
                          record_id   BIGINT;
                          record_data JSONB;
                          boost_count INTEGER;
                      BEGIN
                          CASE TG_TABLE_NAME
                              WHEN 'guild_settings' THEN 
                                  record_id := NEW.guild_id;
                                  record_data := NEW.settings;
                              WHEN 'dict' THEN 
                                  record_id := NEW.guild_id;
                                  record_data := NULL;
                              WHEN 'user_settings' THEN 
                                  record_id := NEW.user_id;
                                  record_data := json_build_object(
                                      'speaker', NEW.speaker,
                                      'speed', NEW.speed,
                                      'pitch', NEW.pitch
                                  );
                              WHEN 'guild_boosts' THEN 
                                  record_id := NEW.guild_id;
                                  -- ブーストカウントは絶対値を送信
                                  SELECT COUNT(*) INTO boost_count 
                                  FROM guild_boosts WHERE guild_id = NEW.guild_id;
                                  record_data := json_build_object('count', boost_count);
                              ELSE 
                                  record_id := NULL;
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
                          RETURNS TRIGGER AS

                      $$
                      DECLARE
                          record_id BIGINT;
                          record_data JSONB;
                          boost_count INTEGER;
                      BEGIN
                          CASE TG_TABLE_NAME
                              WHEN 'guild_settings' THEN 
                                  record_id := OLD.guild_id;
                                  record_data := NULL;
                              WHEN 'dict' THEN 
                                  record_id := OLD.guild_id;
                                  record_data := NULL;
                              WHEN 'user_settings' THEN 
                                  record_id := OLD.user_id;
                                  record_data := NULL;
                              WHEN 'guild_boosts' THEN 
                                  record_id := OLD.guild_id;
                                  -- 削除後のブーストカウント（絶対値）
                                  SELECT COUNT(*) INTO boost_count 
                                  FROM guild_boosts WHERE guild_id = OLD.guild_id;
                                  record_data := json_build_object('count', boost_count);
                              ELSE 
                                  record_id := NULL;
                                  record_data := NULL;
                          END CASE;

                          PERFORM pg_notify(
                              'settings_change',
                              json_build_object(
                                  'table', TG_TABLE_NAME,
                                  'operation', 'DELETE',
                                  'id', record_id,
                                  'data', record_data
                              )::text
                          );
                          RETURN OLD;
                      END;

                      $$ LANGUAGE plpgsql;

                      -- guild_settings トリガー
                      DROP TRIGGER IF EXISTS guild_settings_notify ON guild_settings;
                      CREATE TRIGGER guild_settings_notify
                          AFTER INSERT OR UPDATE ON guild_settings
                          FOR EACH ROW
                          EXECUTE FUNCTION notify_settings_change();

                      DROP TRIGGER IF EXISTS guild_settings_delete_notify ON guild_settings;
                      CREATE TRIGGER guild_settings_delete_notify
                          AFTER DELETE ON guild_settings
                          FOR EACH ROW
                          EXECUTE FUNCTION notify_settings_delete();

                      -- dict トリガー
                      DROP TRIGGER IF EXISTS dict_notify ON dict;
                      CREATE TRIGGER dict_notify
                          AFTER INSERT OR UPDATE ON dict
                          FOR EACH ROW
                          EXECUTE FUNCTION notify_settings_change();

                      DROP TRIGGER IF EXISTS dict_delete_notify ON dict;
                      CREATE TRIGGER dict_delete_notify
                          AFTER DELETE ON dict
                          FOR EACH ROW
                          EXECUTE FUNCTION notify_settings_delete();

                      -- user_settings トリガー
                      DROP TRIGGER IF EXISTS user_settings_notify ON user_settings;
                      CREATE TRIGGER user_settings_notify
                          AFTER INSERT OR UPDATE ON user_settings
                          FOR EACH ROW
                          EXECUTE FUNCTION notify_settings_change();

                      DROP TRIGGER IF EXISTS user_settings_delete_notify ON user_settings;
                      CREATE TRIGGER user_settings_delete_notify
                          AFTER DELETE ON user_settings
                          FOR EACH ROW
                          EXECUTE FUNCTION notify_settings_delete();

                      -- guild_boosts トリガー
                      DROP TRIGGER IF EXISTS guild_boosts_notify ON guild_boosts;
                      CREATE TRIGGER guild_boosts_notify
                          AFTER INSERT ON guild_boosts
                          FOR EACH ROW
                          EXECUTE FUNCTION notify_settings_change();

                      DROP TRIGGER IF EXISTS guild_boosts_delete_notify ON guild_boosts;
                      CREATE TRIGGER guild_boosts_delete_notify
                          AFTER DELETE ON guild_boosts
                          FOR EACH ROW
                          EXECUTE FUNCTION notify_settings_delete();
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
                guild_id = int(row['guild_id'])
                try:
                    raw_data = row['settings']
                    if isinstance(raw_data, str):
                        raw_data = json.loads(raw_data)
                    settings = GuildSettings.model_validate(raw_data)
                    self.cache.set_guild_settings_sync(guild_id, settings)
                except Exception as e:
                    logger.error(f"Failed to load guild settings {guild_id}: {e}")

            # ユーザー設定（全件）
            rows = await conn.fetch("SELECT user_id, speaker, speed, pitch FROM user_settings")
            for row in rows:
                self.cache.set_user_setting_sync(int(row['user_id']), {
                    "speaker": row['speaker'],
                    "speed": row['speed'],
                    "pitch": row['pitch']
                })

            # ブーストカウント（ブーストがあるギルドのみ）
            rows = await conn.fetch(
                "SELECT guild_id, COUNT(*) as count FROM guild_boosts GROUP BY guild_id"
            )
            for row in rows:
                self.cache.set_boost_count_sync(int(row['guild_id']), row['count'])

            # グローバル辞書のみロード
            if self.cache.global_dict_id and self.cache.global_dict_id != 0:
                row = await conn.fetchrow(DictQueries.GET_DICT, self.cache.global_dict_id)
                if row:
                    raw_data = row['dict']
                    if isinstance(raw_data, str):
                        raw_data = json.loads(raw_data)
                    self.cache.set_dict_sync(self.cache.global_dict_id, raw_data)
                    logger.info(f"Global dictionary loaded: {len(raw_data)} entries")

        self.cache.mark_initialized()
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
        self._listener_healthy = True
        self._reconnect_attempts = 0
        logger.info("Started listening for database notifications")

        self._listener_task = asyncio.create_task(self._keep_listener_alive())

    async def _keep_listener_alive(self):
        """リスナー接続を維持し、切断時は再接続"""
        while not self._shutdown:
            try:
                await asyncio.sleep(self.LISTENER_HEALTH_CHECK_INTERVAL)

                if self._shutdown:
                    break

                # 接続状態をチェック
                if self._listener_connection is None or self._listener_connection.is_closed():
                    logger.warning("Listener connection lost, reconnecting...")
                    self._listener_healthy = False
                    await self._reconnect_listener()

            except asyncio.CancelledError:
                logger.debug("Listener keep-alive task cancelled")
                break
            except Exception as e:
                logger.error(f"Listener keep-alive error: {e}")
                await asyncio.sleep(self.LISTENER_RECONNECT_DELAY)

    async def _reconnect_listener(self):
        """リスナー接続を再確立し、キャッシュを再同期"""
        while self._reconnect_attempts < self.MAX_RECONNECT_ATTEMPTS and not self._shutdown:
            try:
                self._reconnect_attempts += 1
                logger.info(f"Reconnection attempt {self._reconnect_attempts}/{self.MAX_RECONNECT_ATTEMPTS}")

                # 古い接続をクリーンアップ
                if self._listener_connection and not self._listener_connection.is_closed():
                    try:
                        await self._listener_connection.close()
                    except Exception as e:
                        logger.warning(f"Error closing old listener connection: {e}")

                # 新しい接続を確立
                self._listener_connection = await asyncpg.connect(
                    user=os.getenv("POSTGRES_USER"),
                    password=os.getenv("POSTGRES_PASSWORD"),
                    database=os.getenv("POSTGRES_DB"),
                    host=os.getenv("POSTGRES_HOST"),
                    port=os.getenv("POSTGRES_PORT")
                )

                await self._listener_connection.add_listener('settings_change', self._on_notification)

                # 再接続後にキャッシュを再同期
                await self._resync_cache_after_reconnect()

                self._listener_healthy = True
                self._reconnect_attempts = 0
                logger.success("Listener reconnected and cache resynced successfully")
                return

            except Exception as e:
                logger.error(f"Failed to reconnect listener: {e}")
                await asyncio.sleep(self.LISTENER_RECONNECT_DELAY)

        if not self._shutdown:
            logger.critical("Max reconnection attempts reached, listener is offline")

    async def _resync_cache_after_reconnect(self):
        """リスナー再接続後にキャッシュを再同期"""
        logger.info("Resyncing cache after listener reconnection...")

        # キャッシュバージョンをインクリメント
        self.cache.increment_cache_version()

        async with self.pool.acquire() as conn:
            # アクティブなVC接続中のギルドの辞書を再ロード
            active_guilds = self.cache.get_active_guilds()
            for guild_id in active_guilds:
                try:
                    row = await conn.fetchrow(DictQueries.GET_DICT, guild_id)
                    if row:
                        raw_data = row['dict']
                        if isinstance(raw_data, str):
                            raw_data = json.loads(raw_data)
                        await self.cache.set_dict(guild_id, raw_data)
                    else:
                        await self.cache.set_dict(guild_id, {})
                except Exception as e:
                    logger.error(f"Failed to resync dictionary for guild {guild_id}: {e}")

            # グローバル辞書を再ロード
            if self.cache.global_dict_id and self.cache.global_dict_id != 0:
                row = await conn.fetchrow(DictQueries.GET_DICT, self.cache.global_dict_id)
                if row:
                    raw_data = row['dict']
                    if isinstance(raw_data, str):
                        raw_data = json.loads(raw_data)
                    await self.cache.set_dict(self.cache.global_dict_id, raw_data)

            # ブーストカウントを再ロード（頻繁に変わる可能性があるため）
            rows = await conn.fetch(
                "SELECT guild_id, COUNT(*) as count FROM guild_boosts GROUP BY guild_id"
            )
            for row in rows:
                await self.cache.set_boost_count(int(row['guild_id']), row['count'])

        logger.info("Cache resync completed")

    def _on_notification(self, connection, pid, channel, payload):
        """通知を受け取った時のコールバック（非同期処理をスケジュール）"""
        asyncio.create_task(self._handle_notification_safe(payload))

    async def _handle_notification_safe(self, payload: str):
        """通知を安全に処理（ロック付き）"""
        async with self._notification_lock:
            await self._handle_notification(payload)

    async def _handle_notification(self, payload: str):
        """通知を処理"""
        try:
            import time
            self._last_notification_time = time.time()

            data = json.loads(payload)
            table = data.get('table')
            operation = data.get('operation')
            record_id = data.get('id')
            record_data = data.get('data')

            if record_id is not None:
                record_id = int(record_id)

            logger.debug(f"[NOTIFY] {operation} on {table}, id={record_id}")

            if table == 'guild_settings':
                await self._handle_guild_settings_change(operation, record_id, record_data)
            elif table == 'dict':
                await self._handle_dict_change(operation, record_id)
            elif table == 'user_settings':
                await self._handle_user_settings_change(operation, record_id, record_data)
            elif table == 'guild_boosts':
                await self._handle_boost_change(operation, record_id, record_data)

        except Exception as e:
            logger.error(f"Failed to process notification: {e}")

    async def _handle_guild_settings_change(self, operation: str, guild_id: int, data):
        if operation == 'DELETE':
            await self.cache.invalidate_guild_settings(guild_id)
        else:
            try:
                if isinstance(data, str):
                    data = json.loads(data)
                settings = GuildSettings.model_validate(data)
                await self.cache.set_guild_settings(guild_id, settings)
                logger.debug(f"[Cache] Guild settings updated via NOTIFY: {guild_id}")
            except Exception as e:
                logger.error(f"Failed to update guild settings cache: {e}")
                # 失敗時はキャッシュを無効化してDBフォールバックを強制
                await self.cache.invalidate_guild_settings(guild_id)

    async def _handle_dict_change(self, operation: str, guild_id: int):
        """辞書変更の処理（即座に無効化し、必要時に再取得）"""
        # グローバル辞書は即座に再ロード
        if guild_id == self.cache.global_dict_id:
            if operation == 'DELETE':
                await self.cache.set_dict(guild_id, {})
            else:
                await self._reload_dict(guild_id)
            return

        # 通常の辞書は無効化のみ（次回アクセス時に再取得）
        if self.cache.is_guild_active(guild_id):
            await self.cache.invalidate_dict(guild_id)
            logger.debug(f"[Cache] Dictionary invalidated via NOTIFY: {guild_id}")

    async def _reload_dict(self, guild_id: int):
        """辞書を DB から再取得してキャッシュに格納"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(DictQueries.GET_DICT, guild_id)
                if row:
                    raw_data = row['dict']
                    if isinstance(raw_data, str):
                        raw_data = json.loads(raw_data)
                    await self.cache.set_dict(guild_id, raw_data)
                    logger.debug(f"[Cache] Dictionary reloaded: {guild_id} ({len(raw_data)} entries)")
                else:
                    await self.cache.set_dict(guild_id, {})
        except Exception as e:
            logger.error(f"Failed to reload dictionary for guild {guild_id}: {e}")

    async def _handle_user_settings_change(self, operation: str, user_id: int, data):
        if operation == 'DELETE':
            await self.cache.invalidate_user_setting(user_id)
        else:
            try:
                if isinstance(data, str):
                    data = json.loads(data)
                await self.cache.set_user_setting(user_id, data)
                logger.debug(f"[Cache] User settings updated via NOTIFY: {user_id}")
            except Exception as e:
                logger.error(f"Failed to update user settings cache: {e}")
                await self.cache.invalidate_user_setting(user_id)

    async def _handle_boost_change(self, operation: str, guild_id: int, data):
        """ブースト変更の処理（絶対値で更新）"""
        try:
            if data and isinstance(data, dict) and 'count' in data:
                count = int(data['count'])
                await self.cache.set_boost_count(guild_id, count)
                logger.debug(f"[Cache] Boost count set to {count} via NOTIFY: {guild_id}")
            else:
                # データがない場合は無効化してDBから再取得させる
                await self.cache.invalidate_boost_count(guild_id)
                logger.debug(f"[Cache] Boost count invalidated via NOTIFY: {guild_id}")
        except Exception as e:
            logger.error(f"Failed to update boost count cache: {e}")
            await self.cache.invalidate_boost_count(guild_id)

    # ========================================
    # 辞書の動的ロード/アンロード
    # ========================================
    async def load_guild_dict(self, guild_id: int):
        """VC接続時に辞書をロード"""
        guild_id = int(guild_id)
        await self.cache.add_active_guild(guild_id)

        # 既にロード済みならスキップ
        if self.cache.is_dict_loaded(guild_id):
            return

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(DictQueries.GET_DICT, guild_id)
            if row:
                raw_data = row['dict']
                if isinstance(raw_data, str):
                    raw_data = json.loads(raw_data)
                await self.cache.set_dict(guild_id, raw_data)
            else:
                await self.cache.set_dict(guild_id, {})

        logger.info(f"[{guild_id}] Dictionary loaded for voice session")

    async def unload_guild_dict(self, guild_id: int):
        """VC切断時に辞書をアンロード"""
        guild_id = int(guild_id)
        await self.cache.remove_active_guild(guild_id)
        await self.cache.remove_dict(guild_id)
        logger.info(f"[{guild_id}] Dictionary unloaded after voice session")

    # ========================================
    # 公開API（キャッシュ優先 + Write-through）
    # ========================================
    async def get_guild_settings(self, guild_id: int) -> GuildSettings:
        """ギルド設定を取得"""
        guild_id = int(guild_id)

        # キャッシュをチェック
        cached = await self.cache.get_guild_settings(guild_id)
        if cached is not None:
            return cached

        # キャッシュミス時はDBから取得
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(GuildSettingsQueries.GET_SETTINGS, guild_id)

        if row:
            raw_data = row['settings']
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)
            settings = GuildSettings.model_validate(raw_data)
            await self.cache.set_guild_settings(guild_id, settings)
            return settings

        # DB にも無い場合はデフォルト値を返す（キャッシュには保存しない）
        return GuildSettings()

    async def set_guild_settings(self, guild_id: int, settings: GuildSettings):
        """ギルド設定を保存（Write-through）"""
        guild_id = int(guild_id)
        settings_dict = settings.model_dump()
        settings_json = json.dumps(settings_dict)

        async with self.pool.acquire() as conn:
            await conn.execute(GuildSettingsQueries.SET_SETTINGS, guild_id, settings_json)

        # Write-through: DB書き込み後に即座にキャッシュも更新
        await self.cache.set_guild_settings(guild_id, settings)
        logger.debug(f"[Cache] Guild settings written through: {guild_id}")

    async def get_user_setting(self, user_id: int) -> dict:
        """ユーザー設定を取得"""
        user_id = int(user_id)

        cached = await self.cache.get_user_setting(user_id)
        if cached is not None:
            return cached

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(UserSettingsQueries.GET_SETTINGS, user_id)
            if row:
                data = {"speaker": row['speaker'], "speed": row['speed'], "pitch": row['pitch']}
                await self.cache.set_user_setting(user_id, data)
                return data

        # デフォルト値を返す（キャッシュには保存しない）
        return {"speaker": 1, "speed": 1.0, "pitch": 0.0}

    async def set_user_setting(self, user_id: int, speaker: int, speed: float, pitch: float):
        """ユーザー設定を保存（Write-through）"""
        user_id = int(user_id)

        async with self.pool.acquire() as conn:
            await conn.execute(UserSettingsQueries.SET_SETTINGS, user_id, speaker, speed, pitch)

        # Write-through
        data = {"speaker": speaker, "speed": speed, "pitch": pitch}
        await self.cache.set_user_setting(user_id, data)
        logger.debug(f"[Cache] User settings written through: {user_id}")

    async def get_dict(self, guild_id: int) -> dict:
        """辞書を取得"""
        guild_id = int(guild_id)

        # グローバル辞書ID が 0 の場合は空を返す
        if guild_id == 0:
            return {}

        cached = await self.cache.get_dict(guild_id)
        if cached is not None:
            return cached

        # キャッシュミス時はDBから取得
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(DictQueries.GET_DICT, guild_id)
            if row:
                raw_data = row['dict']
                if isinstance(raw_data, str):
                    raw_data = json.loads(raw_data)

                # VC接続中またはグローバル辞書ならキャッシュに保存
                if self.cache.is_guild_active(guild_id) or guild_id == self.cache.global_dict_id:
                    await self.cache.set_dict(guild_id, raw_data)

                return raw_data

        return {}

    async def add_or_update_dict(self, guild_id: int, dict_data: dict):
        """辞書を保存（Write-through）"""
        guild_id = int(guild_id)
        dict_json = json.dumps(dict_data)

        async with self.pool.acquire() as conn:
            await conn.execute(DictQueries.INSERT_DICT, guild_id, dict_json)

        # Write-through: VC接続中またはグローバル辞書なら即座にキャッシュ更新
        if self.cache.is_guild_active(guild_id) or guild_id == self.cache.global_dict_id:
            await self.cache.set_dict(guild_id, dict_data)
            logger.debug(f"[Cache] Dictionary written through: {guild_id}")

        return True

    async def get_guild_boost_count(self, guild_id: int) -> int:
        """ブーストカウントを取得"""
        guild_id = int(guild_id)

        cached = await self.cache.get_boost_count(guild_id)
        if cached is not None:
            return cached

        # キャッシュミス時は DB から取得
        async with self.pool.acquire() as conn:
            count = await conn.fetchval(BillingQueries.GET_GUILD_BOOST_COUNT, guild_id)

        count = count or 0
        await self.cache.set_boost_count(guild_id, count)
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
    # その他
    # ========================================
    async def get_bot_instances(self) -> list[dict]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, client_id, bot_name, is_active FROM bot_instances WHERE is_active = true ORDER BY id ASC"
            )
            return [dict(r) for r in rows]

    async def get_user_slots_status(self, user_id: int) -> dict:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(BillingQueries.GET_USER_SLOTS_STATUS, str(user_id))
        if row:
            return {"total": row["total_slots"], "used": row["used_slots"]}
        return {"total": 0, "used": 0}

    async def get_guild_booster(self, guild_id: int) -> str | None:
        async with self.pool.acquire() as conn:
            return await conn.fetchval(BillingQueries.GET_GUILD_BOOST_USER, int(guild_id))

    async def activate_guild_boost(self, guild_id: int, user_id: int) -> bool:
        guild_id = int(guild_id)
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
                    guild_id
                )
                if current_guild_boosts >= max_boosts:
                    logger.warning(f"Activate boost failed: Guild at max boosts")
                    return False

                await conn.execute(
                    "INSERT INTO guild_boosts (guild_id, user_id) VALUES ($1::BIGINT, $2)",
                    guild_id,
                    user_id_str
                )

                # Write-through: 新しいカウントを取得してキャッシュ更新
                new_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM guild_boosts WHERE guild_id = $1::BIGINT",
                    guild_id
                )
                await self.cache.set_boost_count(guild_id, new_count)

                logger.info(f"User {user_id_str} boosted guild {guild_id}")
                return True

    async def deactivate_guild_boost(self, guild_id: int, user_id: int) -> bool:
        guild_id = int(guild_id)
        user_id_str = str(user_id)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT ctid FROM guild_boosts WHERE guild_id = $1::BIGINT AND user_id = $2 LIMIT 1 FOR UPDATE",
                    guild_id,
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
                    # Write-through: 新しいカウントを取得してキャッシュ更新
                    new_count = await conn.fetchval(
                        "SELECT COUNT(*) FROM guild_boosts WHERE guild_id = $1::BIGINT",
                        guild_id
                    )
                    await self.cache.set_boost_count(guild_id, new_count)
                    logger.info(f"User {user_id_str} unboosted guild {guild_id}")

                return success

    async def delete_guild_boosts_by_guild(self, guild_id: int):
        guild_id = int(guild_id)

        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM guild_boosts WHERE guild_id = $1::BIGINT", guild_id)

        # Write-through: カウントを0に設定
        await self.cache.set_boost_count(guild_id, 0)
        logger.info(f"Cleared all boosts for guild {guild_id}")

    async def close(self):
        """データベース接続を終了"""
        self._shutdown = True

        # リスナータスクをキャンセル
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        # リスナー接続を閉じる
        if self._listener_connection and not self._listener_connection.is_closed():
            try:
                await self._listener_connection.close()
            except Exception as e:
                logger.warning(f"Error closing listener connection: {e}")

        # メインプールを閉じる
        if self.pool:
            await self.pool.close()

        logger.info("Database connections closed")

    # ========================================
    # ヘルスチェック・診断
    # ========================================
    def is_listener_healthy(self) -> bool:
        """リスナー接続が正常か確認"""
        return self._listener_healthy and self._listener_connection is not None and not self._listener_connection.is_closed()

    def get_diagnostics(self) -> dict:
        """診断情報を取得"""
        import time
        return {
            "listener_healthy": self.is_listener_healthy(),
            "reconnect_attempts": self._reconnect_attempts,
            "last_notification_age": time.time() - self._last_notification_time if self._last_notification_time > 0 else None,
            "cache_stats": self.cache.stats(),
            "pool_size": self.pool.get_size() if self.pool else 0,
            "pool_free_size": self.pool.get_idle_size() if self.pool else 0,
        }

    # ========================================
    # ボイスセッション管理
    # ========================================

    async def save_voice_session(
            self,
            guild_id: int,
            voice_channel_id: int,
            text_channel_id: int,
            bot_id: int
    ) -> None:
        """
        ボイスセッションをデータベースに保存する

        Args:
            guild_id: ギルドID
            voice_channel_id: 接続中のボイスチャンネルID
            text_channel_id: 読み上げ対象のテキストチャンネルID
            bot_id: BotのユーザーID
        """
        guild_id = int(guild_id)
        voice_channel_id = int(voice_channel_id)
        text_channel_id = int(text_channel_id)
        bot_id = int(bot_id)

        async with self.pool.acquire() as conn:
            await conn.execute(
                VoiceSessionQueries.UPSERT_SESSION,
                guild_id,
                voice_channel_id,
                text_channel_id,
                bot_id
            )
        logger.info(f"[{guild_id}] Voice session saved to database (VC: {voice_channel_id}, TC: {text_channel_id})")

    async def delete_voice_session(self, guild_id: int) -> None:
        """
        ボイスセッションをデータベースから削除する

        Args:
            guild_id: ギルドID
        """
        guild_id = int(guild_id)

        async with self.pool.acquire() as conn:
            await conn.execute(VoiceSessionQueries.DELETE_SESSION, guild_id)
        logger.info(f"[{guild_id}] Voice session deleted from database")

    async def get_voice_sessions_by_bot(self, bot_id: int) -> list[dict]:
        """
        特定のBotが持つ全てのボイスセッションを取得する（再起動時の復元用）

        Args:
            bot_id: BotのユーザーID

        Returns:
            セッション情報のリスト
        """
        bot_id = int(bot_id)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(VoiceSessionQueries.GET_SESSIONS_BY_BOT, bot_id)

        return [
            {
                "guild_id": int(row["guild_id"]),
                "voice_channel_id": int(row["voice_channel_id"]),
                "text_channel_id": int(row["text_channel_id"]),
                "connected_at": row["connected_at"]
            }
            for row in rows
        ]

    async def get_voice_session(self, guild_id: int) -> dict | None:
        """
        特定ギルドのボイスセッションを取得する

        Args:
            guild_id: ギルドID

        Returns:
            セッション情報 or None
        """
        guild_id = int(guild_id)

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(VoiceSessionQueries.GET_SESSION, guild_id)

        if row:
            return {
                "guild_id": int(row["guild_id"]),
                "voice_channel_id": int(row["voice_channel_id"]),
                "text_channel_id": int(row["text_channel_id"]),
                "bot_id": int(row["bot_id"]),
                "connected_at": row["connected_at"]
            }
        return None

    async def clear_voice_sessions_by_bot(self, bot_id: int) -> None:
        """
        特定BotのボイスセッションをすべてDBから削除する（起動時のクリーンアップ用）

        Args:
            bot_id: BotのユーザーID
        """
        bot_id = int(bot_id)

        async with self.pool.acquire() as conn:
            await conn.execute(VoiceSessionQueries.DELETE_ALL_SESSIONS_BY_BOT, bot_id)
        logger.info(f"Cleared all voice sessions for bot {bot_id}")