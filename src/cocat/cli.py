import traceback
from contextlib import asynccontextmanager

from anycorn import Config
from anycorn import serve as anycorn_serve
from anyio import Event, run
from cyclopts import App
from fastapi_users.exceptions import UserAlreadyExists

from .app.app import CocatApp
from .app.db import get_db
from .app.schemas import UserCreate, UserUpdate
from .app.users import get_backend

app = App()


@app.command
def serve(
    *,
    host: str = "localhost",
    port: int = 8000,
    update_dir: str = "",
    db_path: str = "./test.db",
):
    """
    Launch a server.

    Args:
        host: The server host name
        port: The server port number
        update_dir: The path to the directory where the room updates are saved
        db_path: The path to the user database
    """
    run(_serve, host, port, update_dir, db_path)  # pragma: nocover


@app.command
def create_user(
    *,
    email: str,
    password: str,
    is_superuser: bool = False,
    db_path: str = "./test.db",
):
    """
    Create a new user in the database.

    Args:
        email: The user e-mail
        password: The user password
        is_superuser: Whether the user is a superuser
        db_path: The path to the user database
    """
    return run(_create_user, email, password, is_superuser, db_path)


def get_user(
    *,
    email: str,
    db_path: str = "./test.db",
):
    """
    Get a user from the database.

    Args:
        email: The user e-mail
        db_path: The path to the user database
    """
    return run(_get_user, email, db_path)


@app.command
def add_user_to_room(
    *,
    email: str,
    room_id: str,
    db_path: str = "./test.db",
):
    """
    Add a user to a room.

    Args:
        email: The user e-mail
        room_id: The room ID to add the user to
        db_path: The path to the user database
    """
    run(_add_user_to_room, email, room_id, db_path)


@app.command
def remove_user_from_room(
    *,
    email: str,
    room_id: str,
    db_path: str = "./test.db",
):
    """
    Remove a user from a room.

    Args:
        email: The user e-mail
        room_id: The room ID to remove the user from
        db_path: The path to the user database
    """
    run(_remove_user_from_room, email, room_id, db_path)


async def _serve(
    host: str, port: int, update_dir: str, db_path: str
):  # pragma: nocover
    config = Config()
    config.bind = [f"{host}:{port}"]
    shutdown_event = Event()
    tb = None
    try:
        cocat_app = CocatApp(update_dir, db_path)
        await anycorn_serve(
            cocat_app.app,  # type: ignore[arg-type]
            config,
            shutdown_trigger=shutdown_event.wait,
            mode="asgi",
        )
    except Exception:
        tb = traceback.format_exc()
    finally:
        if tb is not None:
            print(tb)
        shutdown_event.set()


async def _create_user(email: str, password: str, is_superuser: bool, db_path: str):
    try:
        async with get_user_manager(db_path, True) as user_manager:
            room_id = email[: email.find("@")]
            user = await user_manager.create(
                UserCreate(
                    email=email,
                    password=password,
                    is_superuser=is_superuser,
                    rooms=[room_id],
                )
            )
            print(f"User created {user}")
            return user
    except UserAlreadyExists:
        print(f"User {email} already exists")
        raise


async def _get_user(email: str, db_path: str):
    async with get_user_manager(db_path) as user_manager:
        return await user_manager.get_by_email(email)


async def _add_user_to_room(email: str, room_id: str, db_path: str):
    async with get_user_manager(db_path) as user_manager:
        user = await user_manager.get_by_email(email)
        user_update = UserUpdate(
            email=user.email,
            rooms=list(set(user.rooms) | set([room_id])),
        )
        await user_manager.update(user_update, user, False)


async def _remove_user_from_room(email: str, room_id: str, db_path: str):
    async with get_user_manager(db_path) as user_manager:
        user = await user_manager.get_by_email(email)
        user_update = UserUpdate(
            email=user.email,
            rooms=list(set(user.rooms) - set([room_id])),
        )
        await user_manager.update(user_update, user, False)


@asynccontextmanager
async def get_user_manager(db_path: str, create_db_and_tables: bool = False):
    db = get_db(db_path)
    if create_db_and_tables:
        await db.create_db_and_tables()
    backend = get_backend(db)
    get_async_session_context = asynccontextmanager(db.get_async_session)
    get_user_db_context = asynccontextmanager(db.get_user_db)
    get_user_manager_context = asynccontextmanager(backend.get_user_manager)

    async with get_async_session_context() as session:
        async with get_user_db_context(session) as user_db:
            async with get_user_manager_context(user_db) as user_manager:
                yield user_manager
