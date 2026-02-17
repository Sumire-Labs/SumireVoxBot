import pytest
import asyncio
from src.core.database import Database
import os

# テスト用のDB接続情報
# 本番環境を壊さないよう、必ずテスト用DBを指定すること
os.environ["POSTGRES_USER"] = "user"
os.environ["POSTGRES_PASSWORD"] = "password"
os.environ["POSTGRES_DB"] = "sumire_vox_test"
os.environ["POSTGRES_HOST"] = "localhost"
os.environ["POSTGRES_PORT"] = "5432"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
async def db():
    database = Database()
    await database.connect()
    # テーブル作成
    await database.init_db()
    
    # データクリア
    async with database.pool.acquire() as conn:
        await conn.execute("TRUNCATE users, guild_boosts CASCADE")
    
    yield database
    await database.close()

@pytest.mark.asyncio
async def test_boost_logic(db):
    user_id = 123456789
    guild_id = 987654321
    
    # 1. 初期状態：スロット0
    status = await db.get_user_slots_status(user_id)
    assert status["total"] == 0
    
    # 2. スロットがない状態でブーストを試みる -> 失敗
    success = await db.activate_guild_boost(guild_id, user_id)
    assert success is False
    
    # 3. スロットを手動で付与（Backendの動作を模倣）
    async with db.pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (discord_id, total_slots) VALUES ($1, $2)",
            str(user_id), 1
        )
    
    # スロット反映確認
    status = await db.get_user_slots_status(user_id)
    assert status["total"] == 1
    assert status["used"] == 0
    
    # 4. ブースト適用 -> 成功
    success = await db.activate_guild_boost(guild_id, user_id)
    assert success is True
    
    # ブースト状態確認
    is_boosted = await db.is_guild_boosted(guild_id)
    assert is_boosted is True
    
    booster = await db.get_guild_booster(guild_id)
    assert booster == str(user_id)
    
    status = await db.get_user_slots_status(user_id)
    assert status["used"] == 1
    
    # 5. 重複ブースト試行 -> 失敗
    success_retry = await db.activate_guild_boost(guild_id, user_id)
    assert success_retry is False
    
    # 6. ブースト解除
    success_deactivate = await db.deactivate_guild_boost(guild_id, user_id)
    assert success_deactivate is True
    
    is_boosted_after = await db.is_guild_boosted(guild_id)
    assert is_boosted_after is False
    
    status_after = await db.get_user_slots_status(user_id)
    assert status_after["used"] == 0
