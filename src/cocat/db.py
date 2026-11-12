from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Any
from uuid import UUID

from pycrdt import (
    ArrayEvent,
    Doc,
    Map,
    MapEvent,
    Transaction,
    TransactionEvent,
    YMessageType,
    create_sync_message,
    create_update_message,
    handle_sync_message,
)
from pydantic import BaseModel
from rich.console import Console
from rich.pretty import pprint

from .catalogue import Catalogue
from .event import Event
from .models import CatalogueModel, EventModel


@dataclass
class _Listeners:
    """What the change dispatcher needs to know about one kind of object."""

    model: type[BaseModel]
    get: Callable[[str], Any]
    objects: dict[str, Any]
    on_create: list[Callable[[Any, Any], None]]
    on_delete: dict[str, list[Callable[[Any], None]]]
    on_change: dict[str, dict[str, list[Callable[[Any, Any], None]]]]


def _fields_changed(
    listeners: _Listeners, uuid: str, changes: dict[str, Any], origin: Any
) -> None:
    callbacks = listeners.on_change.get(uuid, {})
    for key, change in changes.items():
        for callback in callbacks.get(key, []):
            callback(origin, _validated(listeners.model, key, change["newValue"]))


def _validated(model: type[BaseModel], key: str, value: Any) -> Any:
    instance = model.__pydantic_validator__.validate_assignment(
        model.model_construct(), key, value
    )
    return getattr(instance, key)


class DB:
    """
    A database which holds events and catalogues.
    """

    def __init__(self, doc: Doc | None = None) -> None:
        """
        Creates a database.

        Args:
            doc: An optional [Doc](https://y-crdt.github.io/pycrdt/api_reference/#pycrdt.Doc).
        """
        self._doc: Doc = Doc() if doc is None else doc
        self._catalogue_maps = self._doc.get("catalogues", type=Map)
        self._event_maps = self._doc.get("events", type=Map)
        self._synced: list[DB] = []
        self._catalogue_maps.observe_deep(self._catalogues_changed)
        self._catalogue_delete_callbacks: dict[str, list[Callable[[Any], None]]] = (
            defaultdict(list)
        )
        self._catalogue_create_callbacks: list[Callable[[Any, Any], None]] = []
        self._catalogue_change_callbacks: dict[
            str, dict[str, list[Callable[[Any, Any], None]]]
        ] = defaultdict(lambda: defaultdict(list))
        self._catalogues: dict[str, Catalogue] = {}
        self._event_maps.observe_deep(self._events_changed)
        self._event_delete_callbacks: dict[str, list[Callable[[Any], None]]] = (
            defaultdict(list)
        )
        self._event_create_callbacks: list[Callable[[Any, Any], None]] = []
        self._event_change_callbacks: dict[
            str, dict[str, list[Callable[[Any, Any], None]]]
        ] = defaultdict(lambda: defaultdict(list))
        self._events: dict[str, Event] = {}
        self._catalogue_listeners = _Listeners(
            CatalogueModel,
            self.get_catalogue,
            self._catalogues,
            self._catalogue_create_callbacks,
            self._catalogue_delete_callbacks,
            self._catalogue_change_callbacks,
        )
        self._event_listeners = _Listeners(
            EventModel,
            self.get_event,
            self._events,
            self._event_create_callbacks,
            self._event_delete_callbacks,
            self._event_change_callbacks,
        )

    def __repr__(self) -> str:
        console = Console()
        with console.capture() as capture:
            pprint(self.to_dict(), console=console, max_length=8)
        return capture.get()

    def _callback(
        self, callback: Callable[..., None], origin: DB | None, *args: Any
    ) -> None:
        if origin is not self:
            callback(*args)

    def transaction(self) -> Transaction:
        return self._doc.transaction(self)

    @classmethod
    def from_dict(cls, db_dict: dict[str, Any], doc: Doc | None = None) -> DB:
        """
        Creates a database from a dictionary.

        Args:
            db_dict: The dictionary.
            doc: An optional [Doc](https://y-crdt.github.io/pycrdt/api_reference/#pycrdt.Doc).

        Returns:
            The created database.
        """
        db = DB(doc=doc)
        with db.transaction():
            for item in db_dict["events"]:
                db.create_event(**item)
            for item in db_dict["catalogues"]:
                events = [db.get_event(uuid) for uuid in item.pop("events", [])]
                db.create_catalogue(events=events, **item)
            return db

    @classmethod
    def from_json(cls, data: str, doc: Doc | None = None) -> DB:
        """
        Creates a database from a JSON string.

        Args:
            data: The JSON string.
            doc: An optional [Doc](https://y-crdt.github.io/pycrdt/api_reference/#pycrdt.Doc).

        Returns:
            The created database.
        """
        return DB.from_dict(json.loads(data), doc)

    @property
    def doc(self) -> Doc:
        """
        Returns:
            The database [Doc](https://y-crdt.github.io/pycrdt/api_reference/#pycrdt.Doc).
        """
        return self._doc

    def _catalogues_changed(
        self, events: list[ArrayEvent | MapEvent], transaction: Transaction
    ) -> None:
        self._dispatch(self._catalogue_listeners, events, transaction.origin)

    def _events_changed(self, events: list[MapEvent], transaction: Transaction) -> None:
        self._dispatch(self._event_listeners, events, transaction.origin)

    def _dispatch(self, listeners: _Listeners, events: list[Any], origin: Any) -> None:
        for event in events:
            path, changes = event.path, event.keys
            if len(path) == 0:
                self._objects_created_or_deleted(listeners, changes, origin)
            elif len(path) == 1:
                _fields_changed(listeners, path[0], changes, origin)
            elif len(path) == 2:
                uuid, name = path
                self._set_changed(listeners, uuid, name, changes, origin)

    def _objects_created_or_deleted(
        self, listeners: _Listeners, changes: dict[str, Any], origin: Any
    ) -> None:
        for uuid, change in changes.items():
            if change["action"] == "delete":
                for delete_callback in listeners.on_delete.pop(uuid, []):
                    delete_callback(origin)
                listeners.objects.pop(uuid, None)
                listeners.on_change.pop(uuid, None)
            elif change["action"] == "add":
                for callback in listeners.on_create:
                    callback(origin, listeners.get(uuid))

    def _set_changed(
        self,
        listeners: _Listeners,
        uuid: str,
        name: str,
        changes: dict[str, Any],
        origin: Any,
    ) -> None:
        callbacks = listeners.on_change.get(uuid, {})
        removed = {
            key for key, change in changes.items() if change["action"] == "delete"
        }
        added = {
            key: change["newValue"]
            for key, change in changes.items()
            if change["action"] in ("add", "update")
        }
        if removed:
            for callback in callbacks.get(f"remove_{name}", []):
                callback(origin, removed)
        value = self._catalogue_events(added) if name == "events" else added
        if value:
            for callback in callbacks.get(f"add_{name}", []):
                callback(origin, value)

    def _catalogue_events(self, uuids: Iterable[str]) -> set[Event]:
        # An event deleted elsewhere can still be added to a catalogue by a merge.
        return {
            Event._from_map(self._event_maps[uuid], self)
            for uuid in uuids
            if uuid in self._event_maps
        }

    @property
    def catalogues(self) -> set[Catalogue]:
        """
        Returns:
            The catalogues in the database.
        """
        return {
            Catalogue._from_map(self._catalogue_maps[uuid], self)
            for uuid in sorted(self._catalogue_maps.keys())
        }

    @property
    def events(self) -> set[Event]:
        """
        Returns:
            The events in the database.
        """
        return {
            Event._from_map(self._event_maps[uuid], self)
            for uuid in sorted(self._event_maps.keys())
        }

    def create_catalogue(
        self,
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
        with self.transaction():
            kwargs: dict[str, Any] = {
                "name": name,
                "author": author,
            }
            if uuid is not None:
                kwargs["uuid"] = uuid
            if tags is not None:
                kwargs["tags"] = tags
            if attributes is not None:
                kwargs["attributes"] = attributes
            model = CatalogueModel(**kwargs)
            catalogue = Catalogue._new(model, self)
            self._catalogue_maps[str(model.uuid)] = catalogue._map
            if events is not None:
                if isinstance(events, Event):
                    events = [events]
                catalogue.add_events(events)

        return catalogue

    def create_event(
        self,
        *,
        start: datetime | float | str,
        stop: datetime | float | str,
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
        with self.transaction():
            kwargs: dict[str, Any] = {
                "author": author,
                "start": start,
                "stop": stop,
            }
            if uuid is not None:
                kwargs["uuid"] = uuid
            if tags is not None:
                kwargs["tags"] = tags
            if attributes is not None:
                kwargs["attributes"] = attributes
            if products is not None:
                kwargs["products"] = products
            if rating is not None:
                kwargs["rating"] = rating
            model = EventModel(**kwargs)
            event = Event._new(model, self)
            self._event_maps[str(model.uuid)] = event._map
            return event

    def on_create_catalogue(self, callback: Callable[[Catalogue], None]) -> None:
        """
        Registers a callback to be called when a catalogue is created.

        Args:
            callback: The callback to call with the created catalogue.
        """
        self._catalogue_create_callbacks.append(partial(self._callback, callback))

    def on_create_event(self, callback: Callable[[Event], None]) -> None:
        """
        Registers a callback to be called when an event is created.

        Args:
            callback: The callback to call with the created event.
        """
        self._event_create_callbacks.append(partial(self._callback, callback))

    def get_catalogue(self, uuid_or_name: UUID | str) -> Catalogue:
        """
        Args:
            uuid_or_name: The UUID of the catalogue to get, or its name.

        Returns:
            The catalogue with the given UUID or name.
        """
        uuid_or_name = str(uuid_or_name)
        try:
            catalogue = Catalogue._from_uuid(uuid_or_name, self)
        except KeyError:
            for uuid in self._catalogue_maps:
                if self._catalogue_maps[uuid]["name"] == uuid_or_name:
                    catalogue = Catalogue._from_uuid(uuid, self)
                    break
            else:
                raise RuntimeError(
                    f"No catalogue found with name or UUID: {uuid_or_name}"
                )
        return catalogue

    def get_event(self, uuid: UUID | str) -> Event:
        """
        Args:
            uuid: The UUID of the event to get.

        Returns:
            The event with the given UUID.
        """
        uuid = str(uuid)
        try:
            return Event._from_uuid(uuid, self)
        except KeyError:
            raise RuntimeError(f"No event found with UUID: {uuid}")

    def _handle_sync_message(self, message: bytes, db: DB, init: bool = False) -> None:
        if init:
            _message = create_sync_message(self._doc)
            db._handle_sync_message(_message, self)

        message_type = message[0]
        if message_type == YMessageType.SYNC:
            try:
                reply = handle_sync_message(message[1:], self._doc)
                if reply is not None:
                    db._handle_sync_message(reply, self)
            except RuntimeError as exc:
                if str(exc) not in (
                    "Already mutably borrowed",
                    "Already in a transaction",
                ):  # pragma: nocover
                    raise

    def sync(self, db: DB) -> None:
        """
        Keeps the database in sync with another database. Mostly used for tests.

        Args:
            db: The database to keep in sync with this one.
        """
        if db in self._synced or self in db._synced:
            return

        self._synced.append(db)
        message = create_sync_message(self._doc)
        db._handle_sync_message(message, self, True)

        self._doc.observe(partial(send_update, db, self))
        db._doc.observe(partial(send_update, self, db))

    def to_dict(self) -> dict[str, Any]:
        """
        Returns:
            The database as a dictionary.
        """
        db_dict = {
            "events": sorted(
                [event.to_dict() for event in self.events],
                key=lambda event: event["uuid"],
            ),
            "catalogues": sorted(
                [catalogue.to_dict(True) for catalogue in self.catalogues],
                key=lambda catalogue: catalogue["uuid"],
            ),
        }
        events = db_dict["events"]
        for idx, event_dict in enumerate(events):
            event_dict = {key: event_dict[key] for key in EventModel.model_fields}
            events[idx] = event_dict
        return db_dict

    def to_json(self) -> str:
        """
        Returns:
            The database as a JSON string.
        """
        return json.dumps(self.to_dict())


def send_update(destination: DB, source: DB, event: TransactionEvent) -> None:
    message = create_update_message(event.update)
    destination._handle_sync_message(message, source)
