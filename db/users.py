import json
from typing import List, Dict, Optional
from db.manager import AsyncDatabaseManager
from db.schemas import (
    create_users_table_sql,
    insert_users_sql,
    select_all_sql,
    select_user_address_sql,
    select_user_track_addresses_sql,
    clear_table_sql,
    update_address,
    update_track_addresses
)
from utils.customprint import CustomPrint

class UsersSQL:
    def __init__(self, db: AsyncDatabaseManager):
        self.db = db

    async def create_tables(self):
        try:
            await self.db.execute(create_users_table_sql())
            CustomPrint().success("✅ Таблица 'users' создана")
        except Exception as e:
            CustomPrint().error(f"❌ Ошибка при создании таблиц: {e}")
            raise

    async def add_user(self, user: Dict):
        """Добавить пользователя с основным адресом и пустым списком кошельков для трека"""
        try:
            await self.db.execute(insert_users_sql("users"), {
                "tg_id": user.get("tg_id"),
                "address": user.get("address"),
                "track_addresses": json.dumps([])
            })
            CustomPrint().success(f"👤 Пользователь {user.get('tg_id')} добавлен")
        except Exception as e:
            CustomPrint().error(f"Ошибка добавления пользователя {user.get('tg_id')}: {e}")

    async def update_user_address(self, tg_id: int, new_address: str):
        """Обновление основного адреса"""
        try:
            await self.db.execute(update_address(), {"tg_id": tg_id, "address": new_address})
            CustomPrint().success(f"Адрес пользователя {tg_id} обновлен на {new_address}")
        except Exception as e:
            CustomPrint().error(f"Ошибка при обновлении адреса пользователя {tg_id}: {e}")

    async def get_all_data(self) -> List[Dict]:
        return await self.db.fetchall(select_all_sql("users"))

    async def clear_users(self):
        """Очистить таблицу пользователей"""
        await self.db.execute(clear_table_sql("users"))
        CustomPrint().warning("⚠️ Таблица 'users' очищена")

    async def select_user_address(self, tg_id: int) -> Optional[str]:
        try:
            row = await self.db.fetchone(select_user_address_sql(), {"tg_id": tg_id})
            if row:
                return row["address"]
            return None
        except Exception as e:
            CustomPrint().error(f"Ошибка при получении адреса для tg_id={tg_id}: {e}")
            return None

    async def add_track_wallet(self, tg_id: int, wallet: str):
        """Добавить кошелек для копи-трейда"""
        try:
            row = await self.db.fetchone(select_user_track_addresses_sql(), {"tg_id": tg_id})
            wallets = json.loads(row["track_addresses"]) if row and row["track_addresses"] else []
            if wallet not in wallets:
                wallets.append(wallet)
                await self.db.execute(update_track_addresses(), {
                    "tg_id": tg_id,
                    "track_addresses": json.dumps(wallets)
                })
                CustomPrint().success(f"➕ Кошелек для трека {wallet} добавлен пользователю {tg_id}")
        except Exception as e:
            CustomPrint().error(f"Ошибка при добавлении кошелька для трека {tg_id}: {e}")

    async def remove_track_wallet(self, tg_id: int, wallet: str):
        """Удалить кошелек из копи-трейда"""
        try:
            row = await self.db.fetchone(select_user_track_addresses_sql(), {"tg_id": tg_id})
            wallets = json.loads(row["track_addresses"]) if row and row["track_addresses"] else []
            if wallet in wallets:
                wallets.remove(wallet)
                await self.db.execute(update_track_addresses(), {
                    "tg_id": tg_id,
                    "track_addresses": json.dumps(wallets)
                })
                CustomPrint().success(f"❌ Кошелек для трека {wallet} удален у пользователя {tg_id}")
        except Exception as e:
            CustomPrint().error(f"Ошибка при удалении кошелька для трека {tg_id}: {e}")

    async def get_track_wallets(self, tg_id: int) -> List[str]:
        """Получить все кошельки для копи-трейда"""
        try:
            row = await self.db.fetchone(select_user_track_addresses_sql(), {"tg_id": tg_id})
            return json.loads(row["track_addresses"]) if row and row["track_addresses"] else []
        except Exception as e:
            CustomPrint().error(f"Ошибка при получении кошельков для трека {tg_id}: {e}")
            return []
