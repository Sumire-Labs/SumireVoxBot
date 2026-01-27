class GuildDictQueries:
    CREATE_TABLE = """
                   CREATE TABLE IF NOT EXISTS guild_dict
                   (
                       guild_id BIGINT,
                       word     TEXT,
                       reading  TEXT,
                       PRIMARY KEY (guild_id, word)
                   )
                   """

    GET_DICT = """
               SELECT word, reading
               FROM guild_dict
               WHERE guild_id = $1
               """

    INSERT_WORD = """
                  INSERT INTO guild_dict (guild_id, word, reading)
                  VALUES ($1, $2, $3)
                  ON CONFLICT (guild_id, word) DO UPDATE SET reading = EXCLUDED.reading
                  """

    REMOVE_WORD = """
                  DELETE
                  FROM guild_dict
                  WHERE guild_id = $1
                    AND word = $2
                  """

    GET_DICT_WORDS = """
                     SELECT word, reading
                     FROM guild_dict
                     WHERE guild_id = $1
                     ORDER BY word
                     """

