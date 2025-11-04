from typing import List, Dict, Optional
from db.manager import AsyncDatabaseManager
from db.schemas import (
    create_users_table_sql,
    insert_users_sql,
    select_all_sql,
    select_user_address_sql,
    clear_table_sql,
    update_address
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
        try:
            await self.db.execute(insert_users_sql("users"), user)
            CustomPrint().success(f"👤 Пользователь {user.get('tg_id')} добавлен")
        except Exception as e:
            CustomPrint().error(f"Ошибка добавления пользователя {user.get('tg_id')}: {e}")

    async def update_user_address(self, tg_id: int, new_address: str):
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
