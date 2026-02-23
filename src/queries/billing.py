class BillingQueries:
    CREATE_USERS_TABLE = """
                         CREATE TABLE IF NOT EXISTS users
                         (
                             discord_id         TEXT PRIMARY KEY,
                             stripe_customer_id TEXT UNIQUE,
                             total_slots        INTEGER NOT NULL DEFAULT 0
                         ); \
                         """

    CREATE_BOOSTS_TABLE = """
                          CREATE TABLE IF NOT EXISTS guild_boosts
                          (
                              id       SERIAL PRIMARY KEY,
                              guild_id BIGINT NOT NULL,
                              user_id  TEXT   NOT NULL REFERENCES users (discord_id) ON DELETE CASCADE
                          ); \
                          """

    CREATE_BOOSTS_GUILD_INDEX = "CREATE INDEX IF NOT EXISTS idx_guild_boosts_guild_id ON guild_boosts(guild_id);"
    CREATE_BOOSTS_USER_INDEX = "CREATE INDEX IF NOT EXISTS idx_guild_boosts_user_id ON guild_boosts(user_id);"

    GET_USER_BILLING = "SELECT * FROM users WHERE discord_id = $1"
    GET_USER_BOOSTS = "SELECT * FROM guild_boosts WHERE user_id = $1"
    GET_GUILD_BOOSTS = "SELECT * FROM guild_boosts WHERE guild_id = $1::BIGINT"

    # ブーストの追加
    INSERT_BOOST = "INSERT INTO guild_boosts (guild_id, user_id) VALUES ($1::BIGINT, $2)"

    # ユーザーのスロット状況を取得（ブースト数含む）
    GET_USER_SLOTS_STATUS = """
                            SELECT u.total_slots,
                                   (SELECT COUNT(*) FROM guild_boosts WHERE user_id = u.discord_id) as used_slots
                            FROM users u
                            WHERE u.discord_id = $1 \
                            """

    # 特定のギルドが誰によってブーストされているか
    GET_GUILD_BOOST_USER = "SELECT user_id FROM guild_boosts WHERE guild_id = $1::BIGINT"

    # 特定のギルドがブーストされているか
    CHECK_GUILD_BOOST = "SELECT EXISTS(SELECT 1 FROM guild_boosts WHERE guild_id = $1::BIGINT)"

    # 特定のギルドのブースト数を取得
    GET_GUILD_BOOST_COUNT = "SELECT COUNT(*) FROM guild_boosts WHERE guild_id = $1::BIGINT"

    # ブーストの解除
    DELETE_BOOST = "DELETE FROM guild_boosts WHERE guild_id = $1::BIGINT AND user_id = $2"
