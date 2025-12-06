from enum import Enum

from db.sqlite.crud import UsersSQL
from db.sqlalchemy.crud import UsersORM
from db.database_protocol import UsersBase

class DatabaseType(str, Enum):
    SQLITE = "sqlite"
    SQLALCHEMY = "sqlalchemy"


class UsersFactory:

    @staticmethod
    def create(db_type: DatabaseType, connection) -> UsersBase:
        """
        Создает репозиторий пользователей в зависимости от типа БД
        
        Args:
            db_type: Тип базы данных
            connection: Подключение к БД (AsyncDatabaseManager или AsyncSession)
            
        Returns:
            Экземпляр UsersBase (UsersSQL или UsersORM)
        """
        if db_type == DatabaseType.SQLITE:
            return UsersSQL(connection)
        elif db_type == DatabaseType.SQLALCHEMY:
            return UsersORM(connection)
        else:
            raise ValueError(f"Unsupported database type: {db_type}")