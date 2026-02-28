# src/queries/voice_sessions.py

class VoiceSessionQueries:
    """ボイスセッション（接続中のVC・読み上げチャンネル）のクエリ"""

    CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS voice_sessions (
        guild_id BIGINT PRIMARY KEY,
        voice_channel_id BIGINT NOT NULL,
        text_channel_id BIGINT NOT NULL,
        bot_id BIGINT NOT NULL,
        connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
    );
    """

    # Bot ID でフィルタしたインデックス（複数Bot対応）
    CREATE_BOT_INDEX = """
    CREATE INDEX IF NOT EXISTS idx_voice_sessions_bot_id ON voice_sessions (bot_id);
    """

    # セッションを保存（UPSERT）
    UPSERT_SESSION = """
    INSERT INTO voice_sessions (guild_id, voice_channel_id, text_channel_id, bot_id, connected_at)
    VALUES ($1, $2, $3, $4, NOW())
    ON CONFLICT (guild_id) 
    DO UPDATE SET 
        voice_channel_id = EXCLUDED.voice_channel_id,
        text_channel_id = EXCLUDED.text_channel_id,
        bot_id = EXCLUDED.bot_id,
        connected_at = NOW();
    """

    # セッションを削除
    DELETE_SESSION = """
    DELETE FROM voice_sessions WHERE guild_id = $1;
    """

    # 特定のBot IDのセッションを全取得（再起動時の復元用）
    GET_SESSIONS_BY_BOT = """
    SELECT guild_id, voice_channel_id, text_channel_id, connected_at 
    FROM voice_sessions 
    WHERE bot_id = $1;
    """

    # 特定ギルドのセッションを取得
    GET_SESSION = """
    SELECT guild_id, voice_channel_id, text_channel_id, bot_id, connected_at
    FROM voice_sessions
    WHERE guild_id = $1;
    """

    # 全セッションを削除（特定Botの全セッション削除用）
    DELETE_ALL_SESSIONS_BY_BOT = """
    DELETE FROM voice_sessions WHERE bot_id = $1;
    """
