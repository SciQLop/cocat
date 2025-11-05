from asyncio import Task, create_task
from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

import anyio
import httpx
from wiredb import connect as wire_connect

from cocat import DB, Catalogue, Event


class Session:
    def __init__(
        self,
        host: str = "http://localhost",
        port: int = 8000,
        file_path: str = "updates.y",
        room_id: str = "room0",
    ):
        self.host = host
        self.port = port
        self.cookies = httpx.Cookies()
        self.file_path = file_path
        self.room_id = room_id
        self.db = DB()
        self.task: Task | None = None
        self.connected = anyio.Event()
        self.send_stream, self.receive_stream = anyio.create_memory_object_stream()

    def check_connected(self) -> None:
        if not self.connected.is_set():
            raise RuntimeError("Not logged in")

    async def connect(self) -> None:
        try:
            async with wire_connect(
                "websocket",
                id=f"room/{self.room_id}",
                doc=self.db.doc,
                auto_update=False,
                host=self.host,
                port=self.port,
                cookies=self.cookies,
            ) as self.client:
                async with wire_connect(
                    "file", doc=self.db.doc, path=self.file_path
                ) as self.file:
                    self.connected.set()
                    await self.send_stream.send(None)
                    await anyio.sleep_forever()
        except Exception as exc:
            await self.send_stream.send(exc)


SESSION = Session()


def set_config(
    *,
    host: str | None = None,
    port: int | None = None,
    file_path: str | None = None,
    room_id: str | None = None,
) -> None:
    """
    Sets the configuration of the current session.

    Args:
        host: The host name of the database web server.
        port: The port number of the database web server.
        file_path: The path to the file where updates will be stored.
        room_id: The ID of the room to connect to.
    """
    if host is not None:
        SESSION.host = host
    if port is not None:
        SESSION.port = port
    if file_path is not None:
        SESSION.file_path = file_path
    if room_id is not None:
        SESSION.room_id = room_id


async def wait_connected() -> None:
    res = await SESSION.receive_stream.receive()
    if res is not None:
        raise res


async def synchronize() -> None:
    await SESSION.receive_stream.receive()
    SESSION.client.pull()
    await SESSION.client.synchronized.wait()


def connect() -> None:
    SESSION.task = create_task(SESSION.connect())


def log_in(username: str, password: str) -> None:
    """
    Log into the server.

    Args:
        username: The username to use to log in.
        password: The password to use to log in.
    """
    data = {"username": username, "password": password}
    response = httpx.post(f"{SESSION.host}:{SESSION.port}/auth/jwt/login", data=data)
    cookie = response.cookies.get("fastapiusersauth")
    assert cookie is not None
    SESSION.cookies.set("fastapiusersauth", cookie)
    connect()


def log_out() -> None:
    """
    Log out of the server.
    """
    httpx.post(
        f"{SESSION.host}:{SESSION.port}/auth/jwt/logout", cookies=SESSION.cookies
    )
    SESSION.cookies = httpx.Cookies()
    assert SESSION.task is not None
    SESSION.task.cancel()
    SESSION.task = None
    SESSION.connected = anyio.Event()
    SESSION.send_stream, SESSION.receive_stream = anyio.create_memory_object_stream()


def create_catalogue(
    *,
    name: str,
    author: str,
    uuid: UUID | str | bytes | bytearray | None = None,
    tags: list[str] | None = None,
    attributes: dict[str, Any] | None = None,
    events: Iterable[Event] | Event | None = None,
) -> Catalogue:
    """
    Creates a catalogue in the database.

    Args:
        name: The name of the catalogue.
        author: The author of the catalogue.
        uuid: The optional UUID of the catalogue.
        tags: The optional tags of the catalogue.
        attributes: The optional attributes of the catalogue.
        events: The initial event(s) in the catalogue.

    Returns:
        The created [Catalogue][cocat.Catalogue].
    """
    return SESSION.db.create_catalogue(
        name=name,
        author=author,
        uuid=uuid,
        tags=tags,
        attributes=attributes,
        events=events,
    )


def create_event(
    *,
    start: datetime | int | float | str,
    stop: datetime | int | float | str,
    author: str,
    uuid: UUID | str | bytes | bytearray | None = None,
    tags: list[str] | None = None,
    products: list[str] | None = None,
    rating: int | None = None,
    attributes: dict[str, Any] | None = None,
) -> Event:
    """
    Creates an event in the database.

    Args:
        start: The start date of the event.
        stop: The stop date of the event.
        author: The author of the event.
        uuid: The optional UUID of the event.
        tags: The optional tags of the event.
        products: The optional products of the event.
        rating: The optional rating of the event.
        attributes: The optional attributes of the catalogue.

    Returns:
        The created [Event][cocat.Event].
    """
    return SESSION.db.create_event(
        start=start,
        stop=stop,
        author=author,
        uuid=uuid,
        tags=tags,
        products=products,
        rating=rating,
        attributes=attributes,
    )


def get_catalogue(uuid_or_name: UUID | str) -> Catalogue:
    """
    Args:
        uuid_or_name: The UUID or the name of the catalogue to get.

    Returns:
        The catalogue with the given UUID or name.
    """
    return SESSION.db.get_catalogue(uuid_or_name)


def get_event(uuid: UUID | str) -> Event:
    """
    Args:
        uuid: The UUID of the event to get.

    Returns:
        The event with the given UUID.
    """
    return SESSION.db.get_event(uuid)


def refresh() -> None:
    """
    Receives remote changes from the server.
    """
    SESSION.check_connected()
    SESSION.client.pull()


def save() -> None:
    """
    Sends local changes to the server.
    """
    SESSION.check_connected()
    SESSION.client.push()
