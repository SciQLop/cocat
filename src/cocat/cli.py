import contextlib
from functools import partial
from pathlib import Path
from typing import Any

from anycorn import Config, serve as anycorn_serve
from anyio import Event, run, sleep_forever
from anyio.abc import TaskStatus
from cyclopts import App
from fastapi_users.exceptions import UserAlreadyExists
from wiredb import Room, RoomManager, connect

from .app.app import CocatApp
from .app.db import create_db_and_tables, get_async_session, get_user_db
from .app.schemas import UserCreate
from .app.users import get_user_manager

get_async_session_context = contextlib.asynccontextmanager(get_async_session)
get_user_db_context = contextlib.asynccontextmanager(get_user_db)
get_user_manager_context = contextlib.asynccontextmanager(get_user_manager)

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
    run(_serve, host, port, update_dir, db_path)


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
    run(_create_user, email, password, is_superuser, db_path)


class StoredRoom(Room):
    def __init__(self, directory: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._directory = directory

    async def run(self, *args: Any, **kwargs: Any):
        await self.task_group.start(self.connect_to_file)
        await super().run(*args, **kwargs)

    async def connect_to_file(self, *, task_status: TaskStatus[None]) -> None:
        async with connect("file", doc=self.doc, path=f"{Path(self._directory) / self.id.lstrip('/')}.y"):
            task_status.started()
            await sleep_forever()


async def _serve(host: str, port: int, update_dir: str, db_path: str):
    config = Config()
    config.bind = [f"{host}:{port}"]
    shutdown_event = Event()
    try:
        async with RoomManager(partial(StoredRoom, update_dir)) as room_manager:
            cocat_app = CocatApp(room_manager, db_path)
            await anycorn_serve(cocat_app.app, config, shutdown_trigger=shutdown_event.wait, mode="asgi")  # type: ignore[arg-type]
    except Exception:
        shutdown_event.set()


async def _create_user(email: str, password: str, is_superuser: bool = False, db_path = "./test.db"):
    await create_db_and_tables(db_path)

    try:
        async with get_async_session_context() as session:
            async with get_user_db_context(session) as user_db:
                async with get_user_manager_context(user_db) as user_manager:
                    user = await user_manager.create(
                        UserCreate(
                            email=email, password=password, is_superuser=is_superuser
                        )
                    )
                    print(f"User created {user}")
                    return user
    except UserAlreadyExists:
        print(f"User {email} already exists")
        raise


def main():
    app()
