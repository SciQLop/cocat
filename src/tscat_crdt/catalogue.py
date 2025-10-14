import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from json import dumps
from typing import Any, TYPE_CHECKING, cast
from uuid import UUID

from pycrdt import Map

from .event import Event
from .models import CatalogueModel

if sys.version_info >= (3, 11):
    from typing import Self
else:  # pragma: nocover
    from typing_extensions import Self

if TYPE_CHECKING:
    from .db import DB


@dataclass(eq=False)
class Catalogue:
    _uuid: str
    _map: Map
    _db: "DB"

    def _check_deleted(self):
        if self._uuid not in self._db._catalogue_maps:
            raise RuntimeError("Catalogue has been deleted")

    def __eq__(self, other: Any) -> bool:
        self._check_deleted()
        with self._map.doc.transaction():
            if not isinstance(other, Catalogue):
                return NotImplemented

            return self._uuid == other._uuid

    def __repr__(self) -> str:
        with self._map.doc.transaction():
            self._check_deleted()
            dct = self._map.to_py()
            assert dct is not None
            dct["tags"] = [key for key, val in dct["tags"].items()]
            dct["events"] = [key for key, val in dct["events"].items()]
            return dumps(dct)

    def __hash__(self) -> int:
        self._check_deleted()
        return hash(self._uuid)

    def _get(self, name: str) -> Any:
        self._check_deleted()
        value = self._map[name]
        model = CatalogueModel.__pydantic_validator__.validate_assignment(CatalogueModel.model_construct(), name, value)
        return getattr(model, name)

    def _set(self, name: str, value: Any) -> None:
        self._check_deleted()
        model = CatalogueModel.__pydantic_validator__.validate_assignment(CatalogueModel.model_construct(), name, value)
        val = getattr(model, name)
        self._map[name] = val

    def _get_from_map(self, field: str) -> set[str]:
        self._check_deleted()
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            return {key for key in map.keys()}

    def _set_in_map(self, field: str, value: set[str]) -> None:
        self._check_deleted()
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            map.clear()
            method = getattr(self, f"add_{field}")
            for val in value:
                method(val)

    def _on_change(self, name: str, callback: Callable[[Any], None]) -> None:
        self._check_deleted()
        with self._map.doc.transaction():
            self._db._catalogue_change_callbacks[self._uuid][name].append(callback)

    def _add(self, field: str, names: Iterable[str] | str) -> None:
        self._check_deleted()
        name_list = [names] if isinstance(names, str) else names
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            for name in name_list:
                map[name] = True

    def _remove(self, field: str, names: Iterable[str] | str) -> None:
        self._check_deleted()
        name_list = [names] if isinstance(names, str) else names
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            for name in name_list:
                del map[name]

    def _on_add(self, field: str, callback: Callable[[list[Any]], None]):
        self._check_deleted()
        self._db._catalogue_change_callbacks[self._uuid][f"add_{field}"].append(callback)

    def _on_remove(self, field: str, callback: Callable[[list[str]], None]) -> None:
        self._check_deleted()
        self._db._catalogue_change_callbacks[self._uuid][f"remove_{field}"].append(callback)

    @classmethod
    def new(cls, model: CatalogueModel, db: "DB") -> Self:
        uuid = str(model.uuid)
        map = Map(dict(
            uuid=uuid,
            name=model.name,
            author=model.author,
            tags=Map(model.tags),
            events=Map(model.events),
            attributes=Map(model.attributes),
        ))
        self = cls(uuid, map, db)
        db._catalogues[uuid] = self
        return self

    @classmethod
    def from_map(cls, map: Map, db: "DB") -> Self:
        uuid = map["uuid"]
        self = cls(uuid, map, db)
        db._catalogues[uuid] = self
        return self

    @classmethod
    def from_uuid(cls, uuid: str, db: "DB") -> Self:
        map = db._catalogue_maps[uuid]
        self = cls(uuid, map, db)
        db._catalogues[uuid] = self
        return self

    def on_change_name(self, callback: Callable[[Any], None]) -> None:
        self._on_change("name", callback)

    def on_change_author(self, callback: Callable[[Any], None]) -> None:
        self._on_change("author", callback)

    def on_delete(self, callback: Callable[[], None]) -> None:
        with self._map.doc.transaction():
            self._check_deleted()
            self._db._catalogue_delete_callbacks[self._uuid].append(callback)

    def delete(self):
        with self._map.doc.transaction():
            self._check_deleted()
            del self._db._catalogue_maps[self._uuid]

    def on_add_events(self, callback: Callable[[list[Event]], None]) -> None:
        self._on_add("events", callback)

    def on_remove_events(self, callback: Callable[[list[str]], None]) -> None:
        self._on_remove("events", callback)

    def add_events(self, events: Iterable[Event] | Event) -> None:
        self._check_deleted()
        event_list = [events] if isinstance(events, Event) else events
        with self._map.doc.transaction():
            map = cast(Map, self._map["events"])
            for event in event_list:
                map[event._uuid] = True

    def remove_events(self, events: Iterable[Event] | Event) -> None:
        self._check_deleted()
        event_list = [events] if isinstance(events, Event) else events
        with self._map.doc.transaction():
            map = cast(Map, self._map["events"])
            for event in event_list:
                del map[event._uuid]

    def on_add_tags(self, callback: Callable[[list[str]], None]) -> None:
        self._on_add("tags", callback)

    def on_remove_tags(self, callback: Callable[[list[str]], None]) -> None:
        self._on_remove("tags", callback)

    def add_tags(self, names: Iterable[str] | str) -> None:
        self._add("tags", names)

    def remove_tags(self, names: Iterable[str] | str) -> None:
        self._remove("tags", names)

    @property
    def uuid(self) -> UUID:
        return UUID(self._uuid)

    @property
    def name(self) -> str:
        return self._get("name")

    @name.setter
    def name(self, value: str) -> None:
        self._set("name", value)

    @property
    def author(self) -> str:
        return self._get("author")

    @author.setter
    def author(self, value: str) -> None:
        self._set("author", value)

    @property
    def tags(self) -> set[str]:
        return self._get_from_map("tags")

    @tags.setter
    def tags(self, value: set[str]) -> None:
        self._set_in_map("tags", value)

    @property
    def events(self) -> set[Event]:
        self._check_deleted()
        with self._map.doc.transaction():
            event_uuids = cast(Map, self._map["events"])
            return {Event.from_map(self._db._event_maps[uuid], self._db) for uuid, val in event_uuids.items()}

    @events.setter
    def events(self, value: set[Event]) -> None:
        self._check_deleted()
        with self._map.doc.transaction():
            events = cast(Map, self._map["events"])
            events.clear()
            for event in value:
                self.add_events(event)
