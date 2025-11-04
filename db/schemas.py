def create_users_table_sql() -> str:
    return """
    CREATE TABLE IF NOT EXISTS users (
        tg_id INTEGER  PRIMARY KEY,
        address TEXT,
    )
    """

def insert_users_sql(table_name: str) -> str:
    return f"""
    INSERT OR IGNORE INTO {table_name} (
        tg_id, address
    )
    VALUES (
        :tg_id, :address
    )
    """

def select_all_sql(table_name: str) -> str:
    return f"SELECT * FROM {table_name}"

def select_user_address_sql() -> str:
    return "SELECT address FROM users WHERE tg_id = :tg_id"

def clear_table_sql(table_name: str) -> str:
    return f"DELETE FROM {table_name}"
