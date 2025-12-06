import asyncio
from sqlalchemy import select, update, delete, func

from db.sqlalchemy.models import Users, Base
from db.sqlalchemy.session import async_session, async_engine


class AsyncORM:
    @staticmethod
    async def init_db():
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    @staticmethod
    async def add_user(user: Users) -> None:
        async with async_session() as session:
            async with session.begin():
                session.add(user)

    @staticmethod
    async def get_user_by_tg_id(tg_id: int) -> Users | None:
        async with async_session() as session:
            query = select(Users).where(Users.tg_id == tg_id)
            result = await session.execute(query)
            return result.scalar_one_or_none()

    @staticmethod
    async def get_all_users() -> list[Users]:
        async with async_session() as session:
            query = select(Users)
            result = await session.execute(query)
            return result.scalars().all()

    @staticmethod
    async def filter_users(**filters) -> list[Users]:
        """
        Пример:
        await AsyncORM.filter_users(address="0xABC")
        await AsyncORM.filter_users(private_key=None)
        """
        async with async_session() as session:
            query = select(Users)
            for field, value in filters.items():
                query = query.where(getattr(Users, field) == value)

            result = await session.execute(query)
            return result.scalars().all()


    @staticmethod
    async def update_user_fields(tg_id: int, **fields) -> bool:
        """
        Пример:
        await AsyncORM.update_user_fields(123, username="NewName", active=False)
        """
        async with async_session() as session:
            async with session.begin():
                query = select(Users).where(Users.tg_id == tg_id)
                result = await session.execute(query)
                user = result.scalar_one_or_none()

                if not user:
                    return False

                for key, value in fields.items():
                    setattr(user, key, value)

                return True

    @staticmethod
    async def bulk_update(field: str, value):
        """
        Массовое обновление:
        await AsyncORM.bulk_update("address", "0xDEFAULT")
        """
        async with async_session() as session:
            async with session.begin():
                stmt = update(Users).values({field: value})
                await session.execute(stmt)


    @staticmethod
    async def delete_user(tg_id: int) -> bool:
        async with async_session() as session:
            async with session.begin():
                query = select(Users).where(Users.tg_id == tg_id)
                result = await session.execute(query)
                user = result.scalar_one_or_none()

                if not user:
                    return False

                await session.delete(user)
                return True

    @staticmethod
    async def delete_all() -> None:
        async with async_session() as session:
            async with session.begin():
                stmt = delete(Users)
                await session.execute(stmt)

    @staticmethod
    async def user_exists(tg_id: int) -> bool:
        async with async_session() as session:
            query = select(Users.id).where(Users.tg_id == tg_id)
            result = await session.execute(query)
            return result.scalar_one_or_none() is not None

    @staticmethod
    async def count_users() -> int:
        async with async_session() as session:
            query = select(func.count(Users.id))
            result = await session.execute(query)
            return result.scalar()


async def main():
    await AsyncORM.delete_all()
    # user = Users(tg_id=123456789)
    # await AsyncORM.init_db()
    # await AsyncORM.add_user(user)
    # fetched_user = await AsyncORM.get_user_by_tg_id(123456789)
    # print(f'{fetched_user=}')
    # print(fetched_user.tg_id)
    

if __name__ == "__main__":
    asyncio.run(main())
