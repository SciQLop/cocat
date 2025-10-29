from datetime import datetime
from collections.abc import Iterable
from typing import Any
from uuid import UUID

from anyio import Lock
from cocat import DB, Catalogue, Event
from pycrdt import Doc
from wiredb import connect


class Session:
    def __init__(self, host: str = "http://localhost", port: int = 8000, file_path: str = "updates.y"):
        self.catalogues: dict[str, Catalogue] = {}
        self.events: dict[str, Event] = {}
        self.host = host
        self.port = port
        self.file_path = file_path
        self.lock = Lock()

    async def connect(self, doc: Doc) -> None:
        async with self.lock:
            async with connect("websocket", doc=doc, host=self.host, port=self.port) as self.client:
                async with connect("file", doc=doc, path=self.file_path) as self.file:
                    pass

    def create_catalogue(
        self,
        name: str,
        author: str,
        uuid: UUID | str | bytes | bytearray | None = None,
        tags: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
        events: Iterable[Event] | Event | None = None,
    ):
        db = DB()
        catalogue = db.create_catalogue(
            name=name,
            author=author,
            uuid=uuid,
            tags=tags,
            attributes=attributes,
            events=events,
        )
        self.catalogues[str(catalogue.uuid)] = catalogue
        self.catalogues[catalogue.name] = catalogue
        return catalogue

    def create_event(
        self,
        start: datetime | int | float | str,
        stop: datetime | int | float | str,
        author: str,
        uuid: UUID | str | bytes | bytearray | None = None,
        tags: list[str] | None = None,
        products: list[str] | None = None,
        rating: int | None = None,
        attributes: dict[str, Any] | None = None,
    ):
        db = DB()
        event = db.create_event(
            start=start,
            stop=stop,
            author=author,
            uuid=uuid,
            tags=tags,
            products=products,
            rating=rating,
            attributes=attributes,
        )
        self.events[str(event.uuid)] = event
        return event

    def get_local_catalogue(self, uuid_or_name: str) -> Catalogue:
        return self.catalogues[uuid_or_name]

    async def get_remote_catalogue(self, uuid_or_name: str) -> Catalogue:
        db = DB()
        await self.connect(db.doc)
        catalogue = db.get_catalogue(uuid_or_name)
        self.catalogues[str(catalogue.uuid)] = catalogue
        self.catalogues[str(catalogue.name)] = catalogue
        return catalogue

    def get_local_event(self, uuid: str) -> Event:
        return self.events[uuid]

    async def get_remote_event(self, uuid: str) -> Event:
        db = DB()
        await self.connect(db.doc)
        event = db.get_event(uuid)
        self.events[str(event.uuid)] = event
        return event


SESSION = Session()


def set_config(host: str, port: int, file_path: str) -> None:
    SESSION.host = host
    SESSION.port = port
    SESSION.file_path = file_path


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
    return SESSION.create_catalogue(
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
    return SESSION.create_event(
        start=start,
        stop=stop,
        author=author,
        uuid=uuid,
        tags=tags,
        products=products,
        rating=rating,
        attributes=attributes,
    )


async def get_catalogue(uuid_or_name: UUID | str) -> Catalogue:
    return await SESSION.get_remote_catalogue(str(uuid_or_name))


async def save_catalogue(catalogue: Catalogue | UUID | str) -> None:
    if isinstance(catalogue, Catalogue):
        uuid_or_name = str(catalogue.uuid)
    else:
        uuid_or_name = str(catalogue)
    catalogue = SESSION.get_local_catalogue(uuid_or_name)
    await SESSION.connect(catalogue.db.doc)


async def get_event(uuid: UUID | str) -> Event:
    return await SESSION.get_remote_event(str(uuid))


async def save_event(event: Event | UUID | str) -> None:
    if isinstance(event, Event):
        uuid = str(event.uuid)
    else:
        uuid = str(event)
    event = SESSION.get_local_event(uuid)
    await SESSION.connect(event.db.doc)
