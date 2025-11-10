import atexit
from collections.abc import Iterable
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from uuid import UUID

import httpx
from wire_file import FileClient
from wire_websocket import WebSocketClient

from .catalogue import Catalogue
from .db import DB
from .event import Event
from .votable import export_votable_file, import_votable_file


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
        self.connected = False
        self.exit_stack: ExitStack | None = None

    def check_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("Not logged in")

    def connect(self) -> None:
        with ExitStack() as exit_stack:
            self.client = exit_stack.enter_context(
                WebSocketClient(
                    id=f"room/{self.room_id}",
                    doc=self.db.doc,
                    host=self.host,
                    port=self.port,
                    cookies=self.cookies,
                )
            )
            self.file = exit_stack.enter_context(
                FileClient(doc=self.db.doc, path=self.file_path)
            )
            self.exit_stack = exit_stack.pop_all()
            atexit.register(save_on_exit)
            self.connected = True


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


def synchronize() -> None:
    """
    Does the initial synchronization of the client with other peers.
    """
    SESSION.check_connected()
    SESSION.client.pull()


def connect() -> None:
    """
    Launches the connection with the server in the background.
    """
    SESSION.connect()


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
    SESSION.connected = False
    if SESSION.exit_stack is not None:
        SESSION.exit_stack.close()


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


def import_votable(
    file_path: str | Path, table_name: str | None = None
) -> set[Catalogue]:  # pragma: nocover
    """
    Imports a VOTable file into the database.

    Args:
        file_path: The VOTable file path.
    """
    import_votable_file(file_path, SESSION.db, table_name=table_name)
    return SESSION.db.catalogues


def export_votable(
    catalogues: Sequence[Catalogue] | Catalogue, file_path: str | Path
) -> None:  # pragma: nocover
    """
    Exports catalogues to a VOTable file.

    Args:
        catalogues: The catalogue(s) to export.
        file_path: The path to the exported file.
    """
    export_votable_file(catalogues, file_path)


def save_on_exit() -> None:
    response = input("Save changes (Y/n)? ")
    if not response or response.lower().startswith("y"):
        save()
        if SESSION.exit_stack is not None:
            SESSION.exit_stack.__exit__(None, None, None)
            print("Changes have been saved.")
