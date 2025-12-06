from typing import Annotated
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy import Integer, JSON, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

strnullable = Annotated[str | None, mapped_column(String, nullable=True)]

class Base(DeclarativeBase):
    def __repr__(self):
        col = [col for col in self.__table__.columns.keys()]
        return f'{self.__class__.__name__}(' + ', '.join(f'{c}={getattr(self, c)!r}' for c in col) + ')'


class Users(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    track_addresses: Mapped[list[str]] = mapped_column(MutableList.as_mutable(JSON), default=[])
    address: Mapped[strnullable] 
    private_key: Mapped[strnullable] 
    api_key: Mapped[strnullable] 
    api_secret: Mapped[strnullable] 
    api_passphrase: Mapped[strnullable] 