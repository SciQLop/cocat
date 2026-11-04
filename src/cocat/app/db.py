from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config
from anyio import Lock
from fastapi import Depends
from fastapi_users.db import SQLAlchemyBaseUserTableUUID, SQLAlchemyUserDatabase
from fastapi_users_db_sqlalchemy.access_token import (
    SQLAlchemyBaseAccessTokenTableUUID,
)
from sqlalchemy import JSON, Column, Connection, event, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    rooms = Column(JSON, default=[], nullable=False)


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def migration_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def run_migrations(sync_conn: Connection) -> None:
    config = migration_config(sync_conn)
    inspector = inspect(sync_conn)
    if inspector.has_table("user") and not inspector.has_table("alembic_version"):
        command.stamp(config, "0001")
    command.upgrade(config, "head")


@dataclass
class DB:
    async_session_maker: async_sessionmaker[AsyncSession]
    create_db_and_tables: Callable[[], Awaitable]
    get_async_session: Callable[[], AsyncGenerator[AsyncSession, None]]
    get_user_db: Callable[[AsyncSession], AsyncGenerator[SQLAlchemyUserDatabase, None]]


def get_db(path: str) -> DB:
    database_url = f"sqlite+aiosqlite:///{path}"
    engine = create_async_engine(database_url)
    async_session_maker = async_sessionmaker(engine, expire_on_commit=False)
    lock = Lock()

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async def create_db_and_tables():
        async with lock, engine.begin() as conn:
            await conn.run_sync(run_migrations)

    async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
        async with async_session_maker() as session:
            yield session

    async def get_user_db(
        session: AsyncSession = Depends(get_async_session),
    ) -> AsyncGenerator[SQLAlchemyUserDatabase]:
        yield SQLAlchemyUserDatabase(session, User)

    return DB(
        async_session_maker=async_session_maker,
        create_db_and_tables=create_db_and_tables,
        get_async_session=get_async_session,
        get_user_db=get_user_db,
    )
