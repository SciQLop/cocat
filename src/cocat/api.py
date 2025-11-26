import atexit
from collections.abc import Iterable
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse
from uuid import UUID

import httpx
from wire_file import FileClient
from wire_websocket import WebSocketClient

from .catalogue import Catalogue
from .db import DB
from .event import Event
from .votable import export_votable_file, import_votable_file


class Session:
    host = "http://localhost"
    port = 8000
    prefix = ""
    room_id = "room0"
    file_path = "updates.y"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        file_path: str | None = None,
        room_id: str | None = None,
    ):
        self.cookies = httpx.Cookies()
        self.db = DB()
        self.connected = False
        self.exit_stack: ExitStack | None = None
        self.set_config(host=host, port=port, file_path=file_path, room_id=room_id)

    def set_config(
        self,
        host: str | None = None,
        port: int | None = None,
        file_path: str | None = None,
        room_id: str | None = None,
    ) -> None:
        if host is not None:
            parsed_url = urlparse(host)
            self.host = f"{parsed_url.scheme}://{parsed_url.hostname}"
            if parsed_url.port and port is None:
                self.port = parsed_url.port
            self.prefix = parsed_url.path + "/" if parsed_url.path else ""
        if port is not None:
            self.port = port
        if room_id is not None:
            self.room_id = room_id
        if file_path is not None:
            self.file_path = file_path

    def check_connected(self) -> None:
        if not self.connected:
            raise RuntimeError("Not logged in")

    def connect(self) -> None:
        with ExitStack() as exit_stack:
            self.client = exit_stack.enter_context(
                WebSocketClient(
                    id=f"{self.prefix}room/{self.room_id}",
                    doc=self.db.doc,
                    host=self.host,
                    port=self.port,
                    cookies=self.cookies,
                )
            )
            self.file = exit_stack.enter_context(
                FileClient(doc=self.db.doc, path=self.file_path)
            )
            self.client.pull()
            self.file.pull()
            self.exit_stack = exit_stack.pop_all()
            self.connected = True
            atexit.register(save_on_exit)


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
    SESSION.set_config(host=host, port=port, file_path=file_path, room_id=room_id)


def log_in(username: str, password: str) -> None:
    """
    Log into the server.

    Args:
        username: The username to use to log in.
        password: The password to use to log in.
    """
    data = {"username": username, "password": password}
    response = httpx.post(
        f"{SESSION.host}:{SESSION.port}/{SESSION.prefix}auth/jwt/login", data=data
    )
    cookie = response.cookies.get("fastapiusersauth")
    if cookie is None:
        raise RuntimeError("Wrong username or password")
    SESSION.cookies.set("fastapiusersauth", cookie)
    SESSION.connect()


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
    if SESSION.connected:
        response = input("Save changes (Y/n)? ")
        if not response or response.lower().startswith("y"):
            save()
            if SESSION.exit_stack is not None:
                SESSION.exit_stack.close()
                print("Changes have been saved.")
