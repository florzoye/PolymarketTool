import json
import logging
from typing import Dict, List, Optional, Tuple
from db.sqlite.manager import AsyncDatabaseManager

from db.sqlite.schemas import (
    create_users_table_sql,
    insert_users_sql,
    select_user_sql,
    select_all_sql,
    select_user_private_sql,
    select_user_track_addresses_sql,
    update_track_addresses,
    update_private_key,
    update_api_creds,
    get_api_creds,
    clear_table_sql,
    delete_user_sql,
    count_users_sql,
    user_exists_sql,
    select_user_address_sql
)
from db.database_protocol import UsersBase
from db.models import UserModel, to_user_model

class UsersSQL(UsersBase):
    def __init__(self, db: AsyncDatabaseManager):
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)

    async def create_tables(self) -> bool:
        try:
            await self.db.execute(create_users_table_sql())
            return True
        except Exception as e:
            self.logger.error(f"Error creating tables: {e}")
            return False

    async def add_user(self, user: Dict) -> bool:
        try:
            await self.db.execute(insert_users_sql("users"), {
                "tg_id": user.get("tg_id"),
                "address": user.get("address"),
                "track_addresses": json.dumps(user.get("track_addresses", [])),
                "private_key": user.get("private_key"),
                "api_key": user.get("api_key"),
                "api_secret": user.get("api_secret"),
                "api_passphrase": user.get("api_passphrase"),
            })
            return True
        except Exception as e:
            self.logger.error(f"Error adding user: {e}")
            return False

    async def get_user(self, tg_id: int) -> Optional[UserModel]:
        try:
            row = await self.db.fetchone(select_user_sql(), {"tg_id": tg_id})
            if row and row.get("track_addresses"):
                row["track_addresses"] = json.loads(row["track_addresses"])
            return to_user_model(row)
        except Exception as e:
            self.logger.error(f"Error getting user {tg_id}: {e}")
            return None

    async def get_all_users(self) -> List[UserModel]:
        try:
            rows = await self.db.fetchall(select_all_sql("users"))
            users = []
            for row in rows:
                if row.get("track_addresses"):
                    row["track_addresses"] = json.loads(row["track_addresses"])
                user = to_user_model(row)
                if user:
                    users.append(user)
            return users
        except Exception as e:
            self.logger.error(f"Error getting all users: {e}")
            return []

    async def update_user_fields(self, tg_id: int, **fields) -> bool:
        try:
            if not fields:
                return False

            set_clause = ", ".join(f"{k} = :{k}" for k in fields)
            sql = f"UPDATE users SET {set_clause} WHERE tg_id = :tg_id"
            fields["tg_id"] = tg_id
            await self.db.execute(sql, fields)
            return True
        except Exception as e:
            self.logger.error(f"Error updating user {tg_id}: {e}")
            return False

    async def delete_user(self, tg_id: int) -> bool:
        try:
            await self.db.execute(delete_user_sql(), {"tg_id": tg_id})
            return True
        except Exception as e:
            self.logger.error(f"Error deleting user {tg_id}: {e}")
            return False

    async def delete_all(self) -> bool:
        try:
            await self.db.execute(clear_table_sql("users"))
            return True
        except Exception as e:
            self.logger.error(f"Error deleting all users: {e}")
            return False

    async def user_exists(self, tg_id: int) -> bool:
        try:
            row = await self.db.fetchone(user_exists_sql(), {"tg_id": tg_id})
            return row is not None
        except Exception as e:
            self.logger.error(f"Error checking user existence {tg_id}: {e}")
            return False

    async def count_users(self) -> int:
        try:
            row = await self.db.fetchone(count_users_sql())
            return row["cnt"] if row else 0
        except Exception as e:
            self.logger.error(f"Error counting users: {e}")
            return 0

    async def get_track_wallets(self, tg_id: int) -> List[str]:
        try:
            row = await self.db.fetchone(
                select_user_track_addresses_sql(), 
                {"tg_id": tg_id}
            )
            if row and row.get("track_addresses"):
                return json.loads(row["track_addresses"])
            return []
        except Exception as e:
            self.logger.error(f"Error getting track wallets for {tg_id}: {e}")
            return []

    async def add_track_wallet(self, tg_id: int, wallet: str) -> bool:
        try:
            wallets = await self.get_track_wallets(tg_id)
            if wallet not in wallets:
                wallets.append(wallet)
                await self.db.execute(update_track_addresses(), {
                    "tg_id": tg_id,
                    "track_addresses": json.dumps(wallets)
                })
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error adding track wallet for {tg_id}: {e}")
            return False

    async def remove_track_wallet(self, tg_id: int, wallet: str) -> bool:
        try:
            wallets = await self.get_track_wallets(tg_id)
            if wallet in wallets:
                wallets.remove(wallet)
                await self.db.execute(update_track_addresses(), {
                    "tg_id": tg_id,
                    "track_addresses": json.dumps(wallets)
                })
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error removing track wallet for {tg_id}: {e}")
            return False

    async def get_private_key(self, tg_id: int) -> Optional[str]:
        try:
            row = await self.db.fetchone(
                select_user_private_sql(), 
                {"tg_id": tg_id}
            )
            return row["private_key"] if row else None
        except Exception as e:
            self.logger.error(f"Error getting private key for {tg_id}: {e}")
            return None

    async def select_user_address(self, tg_id: int) -> Optional[str]:
        try:
            row = await self.db.fetchone(
                select_user_address_sql(), 
                {"tg_id": tg_id}
            )
            return row["address"] if row else None
        except Exception as e:
            self.logger.error(f"Error getting address for {tg_id}: {e}")
            return None

    async def update_private_key(self, tg_id: int, new_private: str) -> bool:
        try:
            await self.db.execute(update_private_key(), {
                "tg_id": tg_id,
                "private_key": new_private
            })
            return True
        except Exception as e:
            self.logger.error(f"Error updating private key for {tg_id}: {e}")
            return False

    async def update_api_credentials(
        self, tg_id: int, api_key: str, api_secret: str, api_passphrase: str
    ) -> bool:
        try:
            await self.db.execute(update_api_creds(), {
                "tg_id": tg_id,
                "api_key": api_key,
                "api_secret": api_secret,
                "api_passphrase": api_passphrase,
            })
            return True
        except Exception as e:
            self.logger.error(f"Error updating API credentials for {tg_id}: {e}")
            return False

    async def get_api_credentials(
        self, tg_id: int
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        try:
            row = await self.db.fetchone(get_api_creds(), {"tg_id": tg_id})
            if row:
                return row["api_key"], row["api_secret"], row["api_passphrase"]
            return None, None, None
        except Exception as e:
            self.logger.error(f"Error getting API credentials for {tg_id}: {e}")
            return None, None, None