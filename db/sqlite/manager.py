import aiosqlite
from typing import List, Dict, Optional
from utils.customprint import CustomPrint

class AsyncDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        if self._conn is None:
            self._conn = await aiosqlite.connect(self.db_path)
            self._conn.row_factory = aiosqlite.Row  

    async def close(self):
        """Закрыть соединение с базой данных"""
        try:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
                CustomPrint().success("✅ Соединение с БД закрыто")
        except Exception as e:
            CustomPrint().warning(f"⚠️ Ошибка при закрытии БД: {e}")

    async def execute(self, query: str, params: Dict = None):
        await self.connect()
        if params:
            await self._conn.execute(query, params)
        else:
            await self._conn.execute(query)
        await self._conn.commit()

    async def fetchall(self, query: str, params: Dict = None) -> List[Dict]:
        await self.connect()
        cursor = await self._conn.execute(query, params or {})
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def fetchone(self, query: str, params: Dict = None) -> Optional[Dict]:
        await self.connect()
        cursor = await self._conn.execute(query, params or {})
        row = await cursor.fetchone()
        return dict(row) if row else None