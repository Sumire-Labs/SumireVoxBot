import asyncpg
import os

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
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS user_settings
                               (
                                   user_id BIGINT PRIMARY KEY,
                                   speaker INTEGER DEFAULT 1,
                                   speed   REAL    DEFAULT 1.0,
                                   pitch   REAL    DEFAULT 0.0
                               )
                               """)
            # サーバーごとの辞書（ギルド優先・強制置換用）
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS guild_dict
                               (
                                   guild_id BIGINT,
                                   word     TEXT,
                                   reading  TEXT,
                                   PRIMARY KEY (guild_id, word)
                               )
                               """)

    # ユーザー設定の取得
    async def get_user_setting(self, user_id: int):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT speaker, speed, pitch FROM user_settings WHERE user_id = $1",
                user_id
            )
            if row:
                return {"speaker": row['speaker'], "speed": row['speed'], "pitch": row['pitch']}
            return {"speaker": 1, "speed": 1.0, "pitch": 0.0}

    # ユーザー設定の保存
    async def set_user_setting(self, user_id: int, speaker: int, speed: float, pitch: float):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                               INSERT INTO user_settings (user_id, speaker, speed, pitch)
                               VALUES ($1, $2, $3, $4)
                               ON CONFLICT (user_id) DO UPDATE SET speaker = EXCLUDED.speaker,
                                                                   speed   = EXCLUDED.speed,
                                                                   pitch   = EXCLUDED.pitch
                               ''', user_id, speaker, speed, pitch)

    # ギルド辞書の取得（グローバル統合が不要になったためシンプルに）
    async def get_guild_dict(self, guild_id: int):
        """特定のギルドの辞書を辞書形式で取得"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT word, reading FROM guild_dict WHERE guild_id = $1", guild_id)
            return {row['word']: row['reading'] for row in rows}

    # ギルド辞書の登録
    async def set_guild_word(self, guild_id: int, word: str, reading: str):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                               INSERT INTO guild_dict (guild_id, word, reading)
                               VALUES ($1, $2, $3)
                               ON CONFLICT (guild_id, word) DO UPDATE SET reading = EXCLUDED.reading
                               ''', guild_id, word, reading)

    # ギルド辞書の削除
    async def remove_guild_word(self, guild_id: int, word: str):
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM guild_dict WHERE guild_id = $1 AND word = $2",
                guild_id, word
            )
            return result == "DELETE 1"

    # ギルド辞書の一覧取得
    async def get_guild_words(self, guild_id: int):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT word, reading FROM guild_dict WHERE guild_id = $1 ORDER BY word",
                guild_id
            )

    async def close(self):
        if self.pool:
            await self.pool.close()