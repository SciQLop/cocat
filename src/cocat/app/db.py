import enum
import uuid
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
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import (
    JSON,
    Column,
    Connection,
    Enum,
    ForeignKey,
    String,
    event,
    inspect,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    rooms = Column(JSON, default=[], nullable=False)


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    pass


class Role(str, enum.Enum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


ROLE_RANK: dict[Role, int] = {Role.viewer: 0, Role.editor: 1, Role.owner: 2}


class Room(Base):
    __tablename__ = "room"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL")
    )


class Membership(Base):
    __tablename__ = "membership"

    room_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("room.id", ondelete="CASCADE"), primary_key=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[Role] = mapped_column(Enum(Role))
    joined_at: Mapped[datetime] = mapped_column(default=utcnow)


class Invitation(Base):
    __tablename__ = "invitation"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    room_id: Mapped[str] = mapped_column(
        String(255), ForeignKey("room.id", ondelete="CASCADE")
    )
    role: Mapped[Role] = mapped_column(Enum(Role))
    email: Mapped[str | None] = mapped_column(String(320))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    revoked: Mapped[bool] = mapped_column(default=False)
    max_uses: Mapped[int | None]
    uses: Mapped[int] = mapped_column(default=0)


def migration_config(connection: Connection | None = None) -> Config:
    config = Config()
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    if connection is not None:
        config.attributes["connection"] = connection
    return config


def run_migrations(sync_conn: Connection) -> None:
    config = migration_config(sync_conn)
    if inspect(sync_conn).has_table("user") and _version(sync_conn) is None:
        command.stamp(config, "0001")
    command.upgrade(config, "head")


def _version(sync_conn: Connection) -> str | None:
    if not inspect(sync_conn).has_table("alembic_version"):
        return None
    row = sync_conn.execute(text("SELECT version_num FROM alembic_version")).first()
    return row[0] if row else None


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
