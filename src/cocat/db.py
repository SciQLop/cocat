import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from functools import partial
from typing import Any

from pycrdt import (
    ArrayEvent,
    Doc,
    Map,
    MapEvent,
    TransactionEvent,
    YMessageType,
    create_sync_message,
    create_update_message,
    handle_sync_message,
)

from .catalogue import Catalogue
from .event import Event
from .models import CatalogueModel, EventModel


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
        self._catalogue_delete_callbacks: dict[str, list[Callable[[], None]]] = defaultdict(list)
        self._catalogue_create_callbacks: list[Callable[[Any], None]] = []
        self._catalogue_change_callbacks: dict[str, dict[str, list[Callable[[Any], None]]]] = defaultdict(lambda: defaultdict(list))
        self._catalogues: dict[str, Catalogue] = {}
        self._event_maps.observe_deep(self._events_changed)
        self._event_delete_callbacks: dict[str, list[Callable[[], None]]] = defaultdict(list)
        self._event_create_callbacks: list[Callable[[Any], None]] = []
        self._event_change_callbacks: dict[str, dict[str, list[Callable[[Any], None]]]] = defaultdict(lambda: defaultdict(list))
        self._events: dict[str, Event] = {}

    @classmethod
    def from_json(cls, data: str, doc: Doc | None = None) -> "DB":
        """
        Creates a database from a JSON string.

        Args:
            data: The JSON string.
            doc: An optional [Doc](https://y-crdt.github.io/pycrdt/api_reference/#pycrdt.Doc).

        Returns:
            The created database.
        """
        db = DB(doc=doc)
        db_dict = json.loads(data)
        for item in db_dict["events"]:
            db.create_event(EventModel(**item))
        for item in db_dict["catalogues"]:
            db.create_catalogue(CatalogueModel(**item))
        return db

    @property
    def doc(self) -> Doc:
        """
        Returns:
            The database [Doc](https://y-crdt.github.io/pycrdt/api_reference/#pycrdt.Doc).
        """
        return self._doc

    def _catalogues_changed(self, events: list[ArrayEvent | MapEvent]) -> None:
        for event in events:
            path = event.path  # type: ignore[union-attr]
            if len(path) == 0:
                # catalogue created or deleted
                assert isinstance(event, MapEvent)
                keys = event.keys  # type: ignore[attr-defined]
                for uuid in keys:
                    action = keys[uuid]["action"]
                    if action == "delete":
                        for delete_callback in self._catalogue_delete_callbacks[uuid]:
                            delete_callback()
                        if uuid in self._catalogues:
                            del self._catalogues[uuid]
                        del self._catalogue_delete_callbacks[uuid]
                        self._catalogue_change_callbacks
                        del self._catalogue_change_callbacks[uuid]
                    elif action == "add":
                        for create_callback in self._catalogue_create_callbacks:
                            create_callback(self.get_catalogue(uuid))
            elif len(path) == 1:
                # property of catalogue changed (not events)
                assert isinstance(event, MapEvent)
                uuid = path[0]
                changed_keys = event.keys  # type: ignore[attr-defined]
                for key in changed_keys:
                    if key in self._catalogue_change_callbacks[uuid]:
                        callbacks = self._catalogue_change_callbacks[uuid][key]
                        for callback in callbacks:
                            value = changed_keys[key]["newValue"]
                            model = CatalogueModel.__pydantic_validator__.validate_assignment(CatalogueModel.model_construct(), key, value)
                            callback(getattr(model, key))
            elif len(path) == 2:
                if path[1] == "events":
                    # catalogue events changed
                    assert isinstance(event, MapEvent)
                    uuid = path[0]
                    if (
                        "add_events" in self._catalogue_change_callbacks[uuid] or
                        "remove_events" in self._catalogue_change_callbacks[uuid]
                    ):
                        added_uuids = []
                        removed_uuids = []
                        keys = event.keys  # type: ignore[attr-defined]
                        for key, val in keys.items():
                            if val["action"] == "delete":
                                removed_uuids.append(key)
                            else:
                                added_uuids.append(key)
                        if removed_uuids:
                            callbacks = self._catalogue_change_callbacks[uuid]["remove_events"]
                            for callback in callbacks:
                                callback(set(removed_uuids))
                        if added_uuids:
                            result = {Event.from_map(self._event_maps[added_uuid], self) for added_uuid in added_uuids}
                            callbacks = self._catalogue_change_callbacks[uuid]["add_events"]
                            for callback in callbacks:
                                callback(result)
                else:
                    assert isinstance(event, MapEvent)
                    uuid, name = path
                    added = {}
                    removed = set()
                    keys = event.keys  # type: ignore[attr-defined]
                    for key, val in keys.items():
                        if val["action"] == "delete":
                            removed.add(key)
                        elif val["action"] == "add":
                            added[key] = val["newValue"]
                        elif val["action"] == "update":
                            added[key] = val["newValue"]
                    if removed:
                        callbacks = self._catalogue_change_callbacks[uuid][f"remove_{name}"]
                        for callback in callbacks:
                            callback(removed)
                    if added:
                        callbacks = self._catalogue_change_callbacks[uuid][f"add_{name}"]
                        for callback in callbacks:
                            callback(added)

    def _events_changed(self, events: list[MapEvent]) -> None:
        for event in events:
            path = event.path  # type: ignore[attr-defined]
            if len(path) == 0:
                assert isinstance(event, MapEvent)
                keys = event.keys  # type: ignore[attr-defined]
                for uuid in keys:
                    action = keys[uuid]["action"]
                    if action == "delete":
                        for delete_callback in self._event_delete_callbacks[uuid]:
                            delete_callback()
                        if uuid in self._events:
                            del self._events[uuid]
                        del self._event_delete_callbacks[uuid]
                        self._event_change_callbacks[uuid]
                        del self._event_change_callbacks[uuid]
                    elif action == "add":
                        for create_callback in self._event_create_callbacks:
                            create_callback(self.get_event(uuid))
            elif len(path) == 1:
                assert isinstance(event, MapEvent)
                uuid = path[0]
                changed_keys = event.keys  # type: ignore[attr-defined]
                for key in changed_keys:
                    if key in self._event_change_callbacks[uuid]:
                        callbacks = self._event_change_callbacks[uuid][key]
                        for callback in callbacks:
                            value = changed_keys[key]["newValue"]
                            model = EventModel.__pydantic_validator__.validate_assignment(EventModel.model_construct(), key, value)
                            callback(getattr(model, key))
            elif len(path) == 2:
                assert isinstance(event, MapEvent)
                uuid, name = path
                added = {}
                removed = set()
                keys = event.keys  # type: ignore[attr-defined]
                for key, val in keys.items():
                    if val["action"] == "delete":
                        removed.add(key)
                    elif val["action"] == "add":
                        added[key] = val["newValue"]
                    elif val["action"] == "update":
                        added[key] = val["newValue"]
                if removed:
                    callbacks = self._event_change_callbacks[uuid][f"remove_{name}"]
                    for callback in callbacks:
                        callback(removed)
                if added:
                    callbacks = self._event_change_callbacks[uuid][f"add_{name}"]
                    for callback in callbacks:
                        callback(added)

    @property
    def catalogues(self) -> set[Catalogue]:
        """
        Returns:
            The catalogues in the database.
        """
        return {Catalogue.from_map(catalogue, self) for uuid, catalogue in self._catalogue_maps.items()}

    @property
    def events(self) -> set[Event]:
        """
        Returns:
            The events in the database.
        """
        return {Event.from_map(event, self) for uuid, event in self._event_maps.items()}

    def create_catalogue(self, model: CatalogueModel, events: Iterable[Event] | Event | None = None) -> Catalogue:
        """
        Creates a catalogue in the database.

        Args:
            model: The catalogue model.
            events: The initial event(s) in the catalogue.

        Returns:
            The created [Catalogue][cocat.Catalogue].
        """
        catalogue = Catalogue.new(model, self)
        with self._doc.transaction():
            self._catalogue_maps[str(model.uuid)] = catalogue._map
            if events is not None:
                if isinstance(events, Event):
                    events = [events]
                for event in events:
                   catalogue.add_events(event)
        return catalogue

    def create_event(self, model: EventModel) -> Event:
        """
        Creates an event in the database.

        Args:
            model: The event model.

        Returns:
            The created [Event][cocat.Event].
        """
        event = Event.new(model, self)
        self._event_maps[str(model.uuid)] = event._map
        return event

    def on_create_catalogue(self, callback: Callable[[Catalogue], None]) -> None:
        """
        Registers a callback to be called when a catalogue is created.

        Args:
            callback: The callback to call with the created catalogue.
        """
        self._catalogue_create_callbacks.append(callback)

    def on_create_event(self, callback: Callable[[Event], None]) -> None:
        """
        Registers a callback to be called when an event is created.

        Args:
            callback: The callback to call with the created event.
        """
        self._event_create_callbacks.append(callback)

    def get_catalogue(self, uuid: str) -> Catalogue:
        """
        Args:
            uuid: The UUID of the catalogue to get.

        Returns:
            The catalogue with the given UUID.
        """
        return Catalogue.from_uuid(uuid, self)

    def get_event(self, uuid: str) -> Event:
        """
        Args:
            uuid: The UUID of the event to get.

        Returns:
            The event with the given UUID.
        """
        return Event.from_uuid(uuid, self)

    def _handle_sync_message(self, message: bytes, db: "DB", init: bool = False) -> None:
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
                if str(exc) not in ("Already mutably borrowed", "Already in a transaction"):  # pragma: nocover
                    raise

    def sync(self, db: "DB") -> None:
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
        return {
            "catalogues": [catalogue.to_dict() for catalogue in self.catalogues],
            "events": [event.to_dict() for event in self.events],
        }

    def to_json(self) -> str:
        """
        Returns:
            The database as a JSON string.
        """
        return json.dumps(self.to_dict())


def send_update(destination: DB, source: DB, event: TransactionEvent) -> None:
    message = create_update_message(event.update)
    destination._handle_sync_message(message, source)
