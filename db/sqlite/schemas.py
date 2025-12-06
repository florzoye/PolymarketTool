def create_users_table_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS users (
        tg_id INTEGER PRIMARY KEY,
        address TEXT,
        track_addresses TEXT,
        private_key TEXT,
        api_key TEXT,
        api_secret TEXT,
        api_passphrase TEXT
    )
    """


def insert_users_sql(table_name: str) -> str:
    return f"""
    INSERT OR IGNORE INTO {table_name} (
        tg_id, address, track_addresses, private_key, api_key, api_secret, api_passphrase
    )
    VALUES (
        :tg_id, :address, :track_addresses, :private_key, :api_key, :api_secret, :api_passphrase
    )
    """


def select_user_sql() -> str:
    return "SELECT * FROM users WHERE tg_id = :tg_id"


def delete_user_sql() -> str:
    return "DELETE FROM users WHERE tg_id = :tg_id"


def count_users_sql() -> str:
    return "SELECT COUNT(*) AS cnt FROM users"


def user_exists_sql() -> str:
    return "SELECT 1 FROM users WHERE tg_id = :tg_id LIMIT 1"


def update_address() -> str:
    return "UPDATE users SET address = :address WHERE tg_id = :tg_id"


def update_private_key() -> str:
    return "UPDATE users SET private_key = :private_key WHERE tg_id = :tg_id"


def update_track_addresses() -> str:
    return "UPDATE users SET track_addresses = :track_addresses WHERE tg_id = :tg_id"


def select_all_sql(table_name: str) -> str:
    return f"SELECT * FROM {table_name}"


def select_user_address_sql() -> str:
    return "SELECT address FROM users WHERE tg_id = :tg_id"


def select_user_private_sql() -> str:
    return "SELECT private_key FROM users WHERE tg_id = :tg_id"


def select_user_track_addresses_sql() -> str:
    return "SELECT track_addresses FROM users WHERE tg_id = :tg_id"


def clear_table_sql(table_name: str) -> str:
    return f"DELETE FROM {table_name}"


def update_api_creds() -> str:
    return """
    UPDATE users SET 
        api_key = :api_key, 
        api_secret = :api_secret, 
        api_passphrase = :api_passphrase 
    WHERE tg_id = :tg_id
    """


def get_api_creds() -> str:
    return """
    SELECT api_key, api_secret, api_passphrase 
    FROM users 
    WHERE tg_id = :tg_id
    """
