import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from json import dumps
from typing import Any, TYPE_CHECKING

from pycrdt import Map

from .base import Mixin
from .models import EventModel

if sys.version_info >= (3, 11):
    from typing import Self
else:  # pragma: nocover
    from typing_extensions import Self

if TYPE_CHECKING:
    from .db import DB


@dataclass(eq=False)
class Event(Mixin):
    _uuid: str
    _map: Map
    _db: "DB"

    def _check_deleted(self):
        if self._uuid not in self._db._event_maps:
            raise RuntimeError("Event has been deleted")

    def __eq__(self, other: Any) -> bool:
        self._check_deleted()
        with self._map.doc.transaction():
            if not isinstance(other, Event):
                return NotImplemented

            return self._uuid == other._uuid

    def __repr__(self) -> str:
        with self._map.doc.transaction():
            self._check_deleted()
            dct = self._map.to_py()
            assert dct is not None
            dct["tags"] = list(dct["tags"].keys())
            dct["products"] = list(dct["products"].keys())
            return dumps(dct)

    def __hash__(self) -> int:
        self._check_deleted()
        return hash(self._uuid)

    def _get(self, name: str) -> Any:
        self._check_deleted()
        value = self._map[name]
        model = EventModel.__pydantic_validator__.validate_assignment(EventModel.model_construct(), name, value)
        return getattr(model, name)

    def _set(self, name: str, value: Any, func: Callable[[Any], Any] | None = None) -> None:
        self._check_deleted()
        model = EventModel.__pydantic_validator__.validate_assignment(EventModel.model_construct(), name, value)
        val = getattr(model, name)
        if func is not None:
            val = func(val)
        self._map[name] = val

    def _on_change(self, name: str, callback: Callable[[Any], None]) -> None:
        self._check_deleted()
        self._db._event_change_callbacks[self._uuid][name].append(callback)

    def _on_add(self, field: str, callback: Callable[[Any], None]) -> None:
        self._check_deleted()
        self._db._event_change_callbacks[self._uuid][f"add_{field}"].append(callback)

    def _on_remove(self, field: str, callback: Callable[[list[str]], None]) -> None:
        self._check_deleted()
        self._db._event_change_callbacks[self._uuid][f"remove_{field}"].append(callback)

    @classmethod
    def new(cls, model: EventModel, db: "DB") -> Self:
        uuid = str(model.uuid)
        map = Map(dict(
            uuid=uuid,
            start=str(model.start),
            stop=str(model.stop),
            author=model.author,
            tags=Map(model.tags),
            products=Map(model.products),
            rating=model.rating,
            attributes=Map(model.attributes),
        ))
        self = cls(uuid, map, db)
        db._events[uuid] = self
        return self

    @classmethod
    def from_map(cls, map: Map, db: "DB") -> Self:
        uuid = map["uuid"]
        self = cls(uuid, map, db)
        db._events[uuid] = self
        return self

    @classmethod
    def from_uuid(cls, uuid: str, db: "DB") -> Self:
        map = db._event_maps[uuid]
        self = cls(uuid, map, db)
        db._events[uuid] = self
        return self

    def on_change_author(self, callback: Callable[[Any], None]) -> None:
        self._on_change("author", callback)

    def on_change_start(self, callback: Callable[[Any], None]) -> None:
        self._on_change("start", callback)

    def on_change_stop(self, callback: Callable[[Any], None]) -> None:
        self._on_change("stop", callback)

    def on_change_rating(self, callback: Callable[[Any], None]) -> None:
        self._on_change("rating", callback)

    def on_delete(self, callback: Callable[[], None]) -> None:
        self._check_deleted()
        self._db._event_delete_callbacks[self._uuid].append(callback)

    def delete(self):
        self._check_deleted()
        with self._map.doc.transaction():
            del self._db._event_maps[self._uuid]
            for uuid, catalogue in self._db._catalogue_maps.items():
                catalogue_events = catalogue["events"]
                if self._uuid in catalogue_events:
                    del catalogue_events[self._uuid]

    @property
    def start(self) -> datetime:
        return self._get("start")

    @start.setter
    def start(self, value: datetime) -> None:
        self._set("start", value, str)

    @property
    def stop(self) -> datetime:
        return self._get("stop")

    @stop.setter
    def stop(self, value: datetime) -> None:
        self._set("stop", value, str)

    @property
    def rating(self) -> int:
        return self._get("rating")

    @rating.setter
    def rating(self, value: int) -> None:
        self._set("rating", value)

    @property
    def products(self) -> set[str]:
        return set(self._get_from_map("products"))

    @products.setter
    def products(self, value: set[str]) -> None:
        products = {val: True for val in value}
        self._set_in_map("products", products)

    def on_add_products(self, callback: Callable[[set[str]], None]) -> None:

        def _callback(values: dict[str, Any]) -> None:
            callback(set(values))

        self._on_add("products", _callback)

    def on_remove_products(self, callback: Callable[[list[str]], None]) -> None:
        self._on_remove("products", callback)

    def add_products(self, keys: Iterable[str] | str) -> None:
        self._add_keys("products", keys)

    def remove_products(self, keys: Iterable[str] | str) -> None:
        self._remove_keys("products", keys)
