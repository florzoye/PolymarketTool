from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

class UsersBase(ABC):

    @abstractmethod
    async def create_tables(self):
        ...

    @abstractmethod
    async def add_user(self, user: Dict) -> bool:
        ...

    @abstractmethod
    async def get_user(self, tg_id: int):
        ...

    @abstractmethod
    async def get_all_users(self) -> List:
        ...

    @abstractmethod
    async def update_user_fields(self, tg_id: int, **fields) -> bool:
        ...

    @abstractmethod
    async def delete_user(self, tg_id: int) -> bool:
        ...

    @abstractmethod
    async def delete_all(self) -> bool:
        ...

    @abstractmethod
    async def user_exists(self, tg_id: int) -> bool:
        ...

    @abstractmethod
    async def count_users(self) -> int:
        ...

    @abstractmethod
    async def select_user_address(self, tg_id: int) -> Optional[str]:
        ...
        
    @abstractmethod
    async def get_track_wallets(self, tg_id: int) -> List[str] | None:
        ...

    @abstractmethod
    async def add_track_wallet(self, tg_id: int, wallet: str) -> bool:
        ...

    @abstractmethod
    async def remove_track_wallet(self, tg_id: int, wallet: str) -> bool:
        ...

    @abstractmethod
    async def get_private_key(self, tg_id: int) -> Optional[str]:
        ...

    @abstractmethod
    async def update_private_key(self, tg_id: int, new_private: str) -> bool:
        ...

    @abstractmethod
    async def update_api_credentials(
        self, tg_id: int, api_key: str, api_secret: str, api_passphrase: str
    ) -> bool:
        ...

    @abstractmethod
    async def get_api_credentials(
        self, tg_id: int
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        ...