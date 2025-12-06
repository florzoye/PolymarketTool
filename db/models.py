import logging
from pydantic import BaseModel, Field
from typing import List, Optional, Annotated, Union

StrNullable = Annotated[
    Optional[str],
    Field(min_length=1)
]


class UserModel(BaseModel):
    """Pydantic модель пользователя"""
    tg_id: int
    address: StrNullable = None
    track_addresses: List[str] = Field(default_factory=list)
    private_key: StrNullable = None
    api_key: StrNullable = None
    api_secret: StrNullable = None
    api_passphrase: StrNullable = None


def to_user_model(user: Union[dict, object, None]) -> Optional[UserModel]:
    """
    Конвертирует dict или SQLAlchemy объект в UserModel
    
    Args:
        user: dict из SQLite или SQLAlchemy ORM объект или None
        
    Returns:
        UserModel или None
    """
    if not user:
        return None

    try:
        if isinstance(user, dict):
            data = user.copy()
        else:
            data = {k: v for k, v in user.__dict__.items() if not k.startswith("_")}

        if data.get("track_addresses") is None:
            data["track_addresses"] = []

        return UserModel(**data)
        
    except Exception as e:
        logging.error(f"Error converting to UserModel: {e}")
        return None