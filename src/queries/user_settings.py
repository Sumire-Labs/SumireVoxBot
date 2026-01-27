class UserSettingsQueries:
    CREATE_TABLE = """
                   CREATE TABLE IF NOT EXISTS user_settings
                   (
                       user_id BIGINT PRIMARY KEY,
                       speaker INTEGER DEFAULT 1,
                       speed   REAL    DEFAULT 1.0,
                       pitch   REAL    DEFAULT 0.0
                   )
                   """

    GET_SETTINGS = """
                   SELECT speaker, speed, pitch
                   FROM user_settings
                   WHERE user_id = $1
                   """

    SET_SETTINGS = """
                   INSERT INTO user_settings (user_id, speaker, speed, pitch)
                   VALUES ($1, $2, $3, $4)
                   ON CONFLICT (user_id) DO UPDATE SET speaker = EXCLUDED.speaker,
                                                       speed   = EXCLUDED.speed,
                                                       pitch   = EXCLUDED.pitch
                   """