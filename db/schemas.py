def create_users_table_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS users (
        tg_id INTEGER PRIMARY KEY,
        address TEXT,
        track_addresses TEXT
    )
    """

def insert_users_sql(table_name: str) -> str:
    return f"""
    INSERT OR IGNORE INTO {table_name} (
        tg_id, address, track_addresses
    )
    VALUES (
        :tg_id, :address, :track_addresses
    )
    """

def update_address() -> str:
    return "UPDATE users SET address = :address WHERE tg_id = :tg_id"

def update_track_addresses() -> str:
    return "UPDATE users SET track_addresses = :track_addresses WHERE tg_id = :tg_id"

def select_all_sql(table_name: str) -> str:
    return f"SELECT * FROM {table_name}"

def select_user_address_sql() -> str:
    return "SELECT address FROM users WHERE tg_id = :tg_id"

def select_user_track_addresses_sql() -> str:
    return "SELECT track_addresses FROM users WHERE tg_id = :tg_id"

def clear_table_sql(table_name: str) -> str:
    return f"DELETE FROM {table_name}"
