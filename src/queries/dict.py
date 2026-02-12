class DictQueries:
    CREATE_TABLE = """
                   CREATE TABLE IF NOT EXISTS dict
                   (
                       guild_id BIGINT,
                       dict JSONB NOT NULL DEFAULT '{}',
                       PRIMARY KEY (guild_id)
                   )
                   """

    GET_DICT = """
               SELECT dict
               FROM dict
               WHERE guild_id = $1
               """

    INSERT_DICT = """
                  INSERT INTO dict (guild_id, dict)
                  VALUES ($1, $2)
                  ON CONFLICT (guild_id) DO UPDATE SET dict = EXCLUDED.dict
                  """