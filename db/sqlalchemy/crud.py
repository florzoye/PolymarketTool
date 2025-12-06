import logging
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func

from db.sqlalchemy.models import Users
from db.models import UserModel

from db.database_protocol import UsersBase
from db.models import to_user_model

class UsersORM(UsersBase):
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(self.__class__.__name__)

    async def create_tables(self) -> bool:
        return True

    async def add_user(self, user: Dict) -> bool:
        try:
            obj = Users(
                tg_id=user.get("tg_id"),
                address=user.get("address"),
                track_addresses=user.get("track_addresses", []),
                private_key=user.get("private_key"),
                api_key=user.get("api_key"),
                api_secret=user.get("api_secret"),
                api_passphrase=user.get("api_passphrase"),
            )
            self.session.add(obj)
            await self.session.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error adding user: {e}")
            await self.session.rollback()
            return False

    async def get_user(self, tg_id: int) -> Optional[UserModel]:
        try:
            result = await self.session.execute(
                select(Users).where(Users.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            return to_user_model(user)
        except Exception as e:
            self.logger.error(f"Error getting user {tg_id}: {e}")
            return None

    async def get_all_users(self) -> List[UserModel]:
        try:
            result = await self.session.execute(select(Users))
            users = result.scalars().all()
            return [to_user_model(u) for u in users if to_user_model(u)]
        except Exception as e:
            self.logger.error(f"Error getting all users: {e}")
            return []

    async def update_user_fields(self, tg_id: int, **fields) -> bool:
        try:
            if not fields:
                return False

            await self.session.execute(
                update(Users).where(Users.tg_id == tg_id).values(**fields)
            )
            await self.session.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error updating user {tg_id}: {e}")
            await self.session.rollback()
            return False

    async def delete_user(self, tg_id: int) -> bool:
        try:
            await self.session.execute(
                delete(Users).where(Users.tg_id == tg_id)
            )
            await self.session.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error deleting user {tg_id}: {e}")
            await self.session.rollback()
            return False

    async def delete_all(self) -> bool:
        try:
            await self.session.execute(delete(Users))
            await self.session.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error deleting all users: {e}")
            await self.session.rollback()
            return False

    async def user_exists(self, tg_id: int) -> bool:
        try:
            result = await self.session.execute(
                select(Users.tg_id).where(Users.tg_id == tg_id).limit(1)
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            self.logger.error(f"Error checking user existence {tg_id}: {e}")
            return False

    async def count_users(self) -> int:
        try:
            result = await self.session.execute(
                select(func.count()).select_from(Users)
            )
            return result.scalar_one()
        except Exception as e:
            self.logger.error(f"Error counting users: {e}")
            return 0

    async def get_track_wallets(self, tg_id: int) -> List[str]:
        try:
            user = await self.get_user(tg_id)
            return user.track_addresses if user else []
        except Exception as e:
            self.logger.error(f"Error getting track wallets for {tg_id}: {e}")
            return []

    async def add_track_wallet(self, tg_id: int, wallet: str) -> bool:
        try:
            result = await self.session.execute(
                select(Users).where(Users.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return False

            if wallet not in user.track_addresses:
                user.track_addresses.append(wallet)
                await self.session.commit()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error adding track wallet for {tg_id}: {e}")
            await self.session.rollback()
            return False

    async def remove_track_wallet(self, tg_id: int, wallet: str) -> bool:
        try:
            result = await self.session.execute(
                select(Users).where(Users.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                return False

            if wallet in user.track_addresses:
                user.track_addresses.remove(wallet)
                await self.session.commit()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error removing track wallet for {tg_id}: {e}")
            await self.session.rollback()
            return False

    async def get_private_key(self, tg_id: int) -> Optional[str]:
        try:
            user = await self.get_user(tg_id)
            return user.private_key if user else None
        except Exception as e:
            self.logger.error(f"Error getting private key for {tg_id}: {e}")
            return None
    
    async def select_user_address(self, tg_id: int) -> Optional[str]:
        try:
            user = await self.get_user(tg_id)
            return user.address if user else None
        except Exception as e:
            self.logger.error(f"Error getting private key for {tg_id}: {e}")
            return None

    async def update_private_key(self, tg_id: int, new_private: str) -> bool:
        try:
            await self.session.execute(
                update(Users)
                .where(Users.tg_id == tg_id)
                .values(private_key=new_private)
            )
            await self.session.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error updating private key for {tg_id}: {e}")
            await self.session.rollback()
            return False

    async def update_api_credentials(
        self, tg_id: int, api_key: str, api_secret: str, api_passphrase: str
    ) -> bool:
        try:
            await self.session.execute(
                update(Users)
                .where(Users.tg_id == tg_id)
                .values(
                    api_key=api_key,
                    api_secret=api_secret,
                    api_passphrase=api_passphrase,
                )
            )
            await self.session.commit()
            return True
        except Exception as e:
            self.logger.error(f"Error updating API credentials for {tg_id}: {e}")
            await self.session.rollback()
            return False

    async def get_api_credentials(
        self, tg_id: int
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        try:
            result = await self.session.execute(
                select(
                    Users.api_key,
                    Users.api_secret,
                    Users.api_passphrase
                ).where(Users.tg_id == tg_id)
            )
            row = result.first()
            if row:
                return (row.api_key, row.api_secret, row.api_passphrase)
            return None, None, None
        except Exception as e:
            self.logger.error(f"Error getting API credentials for {tg_id}: {e}")
            return None, None, None
