class GuildSettingsQueries:
    CREATE_TABLE = """
                   CREATE TABLE IF NOT EXISTS guild_settings
                   (
                       guild_id BIGINT PRIMARY KEY,
                       settings JSONB NOT NULL DEFAULT '{}'
                   )
                   """

    GET_SETTINGS = """
                   SELECT settings
                   FROM guild_settings
                   WHERE guild_id = $1
                   """

    SET_SETTINGS = """
                   INSERT INTO guild_settings (guild_id, settings)
                   VALUES ($1, $2) ON CONFLICT (guild_id) DO
                   UPDATE SET settings = EXCLUDED.settings
                   """