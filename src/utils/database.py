import asyncpg
import os


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """DB接続プールの作成"""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                user=os.getenv("POSTGRES_USER"),
                password=os.getenv("POSTGRES_PASSWORD"),
                database=os.getenv("POSTGRES_DB"),
                host=os.getenv("POSTGRES_HOST"),
                port=os.getenv("POSTGRES_PORT")
            )

    async def init_db(self):
        """テーブルの初期化。Discord IDは非常に大きいためBIGINTを使用します。"""
        if self.pool is None:
            await self.connect()

        async with self.pool.acquire() as conn:
            await conn.execute('''
                               CREATE TABLE IF NOT EXISTS user_settings
                               (
                                   user_id BIGINT PRIMARY KEY,
                                   speaker INTEGER DEFAULT 1,
                                   speed REAL DEFAULT 1.0,
                                   pitch REAL DEFAULT 0.0
                               )
                               ''')

    async def get_user_setting(self, user_id: int):
        """ユーザー設定の取得。なければデフォルト値を返す。"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT speaker, speed, pitch FROM user_settings WHERE user_id = $1",
                user_id
            )
            if row:
                # 辞書形式で返すと扱いやすい
                return {"speaker": row['speaker'], "speed": row['speed'], "pitch": row['pitch']}
            return {"speaker": 1, "speed": 1.0, "pitch": 0.0}

    async def set_user_setting(self, user_id: int, speaker: int, speed: float, pitch: float):
        """UPSERT (挿入、既にあれば更新)"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                               INSERT INTO user_settings (user_id, speaker, speed, pitch)
                               VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO
                               UPDATE SET
                                   speaker = EXCLUDED.speaker,
                                   speed = EXCLUDED.speed,
                                   pitch = EXCLUDED.pitch
                               ''', user_id, speaker, speed, pitch)

    async def close(self):
        if self.pool:
            await self.pool.close()