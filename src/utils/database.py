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
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS user_settings
                               (
                                   user_id BIGINT PRIMARY KEY,
                                   speaker INTEGER DEFAULT 1,
                                   speed   REAL    DEFAULT 1.0,
                                   pitch   REAL    DEFAULT 0.0
                               )
                               """)
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS guild_dict
                               (
                                   guild_id BIGINT,
                                   word     TEXT,
                                   reading  TEXT,
                                   PRIMARY KEY (guild_id, word)
                               )
                               """)
            await conn.execute("""
                               CREATE TABLE IF NOT EXISTS global_dict
                               (
                                   word    TEXT PRIMARY KEY,
                                   reading TEXT
                               )
                               """)

    # ユーザー設定の取得
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

    # ユーザー設定を設定
    async def set_user_setting(self, user_id: int, speaker: int, speed: float, pitch: float):
        """UPSERT (挿入、既にあれば更新)"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                               INSERT INTO user_settings (user_id, speaker, speed, pitch)
                               VALUES ($1, $2, $3, $4)
                               ON CONFLICT (user_id) DO UPDATE SET speaker = EXCLUDED.speaker,
                                                                   speed   = EXCLUDED.speed,
                                                                   pitch   = EXCLUDED.pitch
                               ''', user_id, speaker, speed, pitch)

    # 辞書を取得してcombinedに統合
    async def get_combined_dict(self, guild_id: int):
        """グローバルとギルド専用を統合して取得。ギルド優先。"""
        async with self.pool.acquire() as conn:
            # グローバルを取得
            global_rows = await conn.fetch("SELECT word, reading FROM global_dict")
            # ギルド専用を取得
            guild_rows = await conn.fetch("SELECT word, reading FROM guild_dict WHERE guild_id = $1", guild_id)

            # 辞書にマッピング (先にグローバルを入れ、後からギルドで上書きすることで優先順位を実現)
            combined = {row['word']: row['reading'] for row in global_rows}
            for row in guild_rows:
                combined[row['word']] = row['reading']

            return combined

    async def set_guild_word(self, guild_id: int, word: str, reading: str):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                               INSERT INTO guild_dict (guild_id, word, reading)
                               VALUES ($1, $2, $3)
                               ON CONFLICT (guild_id, word) DO UPDATE SET reading = EXCLUDED.reading
                               ''', guild_id, word, reading)

    async def set_global_word(self, word: str, reading: str):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                               INSERT INTO global_dict (word, reading)
                               VALUES ($1, $2)
                               ON CONFLICT (word) DO UPDATE SET reading = EXCLUDED.reading
                               ''', word, reading)

    async def remove_guild_word(self, guild_id: int, word: str):
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM guild_dict WHERE guild_id = $1 AND word = $2",
                guild_id, word
            )
            return result == "DELETE 1"  # 1件削除できたらTrue

    async def remove_global_word(self, word: str):
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM global_dict WHERE word = $1",
                word
            )
            return result == "DELETE 1"

    async def get_guild_words(self, guild_id: int):
        """サーバー辞書の一覧のみ取得"""
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT word, reading FROM guild_dict WHERE guild_id = $1 ORDER BY word",
                guild_id
            )

    async def get_global_words(self):
        """グローバル辞書の一覧のみ取得"""
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT word, reading FROM global_dict ORDER BY word")

    async def close(self):
        if self.pool:
            await self.pool.close()
