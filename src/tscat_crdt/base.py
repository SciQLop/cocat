from collections.abc import Callable, Iterable
from typing import Any, cast
from uuid import UUID

from pycrdt import Map

class Mixin:
    _uuid: str
    _map: Map
    _get: Callable[[str], Any]
    _set: Callable[[str, Any], None]
    _check_deleted: Callable[[], None]
    _on_add: Callable[[str, Callable[[Any], None]], None]
    _on_remove: Callable[[str, Callable[[list[str]], None]], None]

    def _get_from_map(self, field: str) -> dict[str, Any]:
        self._check_deleted()
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            res = map.to_py()
            assert res is not None
            return res

    def _set_in_map(self, field: str, value: dict[str, Any]) -> None:
        self._check_deleted()
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            map.clear()
            map.update(value)

    def _add_keys(self, field: str, keys: Iterable[str] | str) -> None:
        self._check_deleted()
        key_list = [keys] if isinstance(keys, str) else keys
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            for key in key_list:
                map[key] = True

    def _add_items(self, field: str, items: dict[str, Any]) -> None:
        self._check_deleted()
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            map.update(items)

    def _remove_keys(self, field: str, keys: Iterable[str] | str) -> None:
        self._check_deleted()
        key_list = [keys] if isinstance(keys, str) else keys
        with self._map.doc.transaction():
            map = cast(Map, self._map[field])
            for key in key_list:
                del map[key]

    def on_set_attributes(self, callback: Callable[[list[str]], None]) -> None:
        self._on_add("attributes", callback)

    def on_remove_attributes(self, callback: Callable[[list[str]], None]) -> None:
        self._on_remove("attributes", callback)

    def set_attributes(self, **kwargs: Any) -> None:
        self._add_items("attributes", kwargs)

    def remove_attributes(self, keys: Iterable[str] | str) -> None:
        self._remove_keys("attributes", keys)

    def on_add_tags(self, callback: Callable[[set[str]], None]) -> None:

        def _callback(values: dict[str, Any]) -> None:
            callback(set(values))

        self._on_add("tags", _callback)

    def on_remove_tags(self, callback: Callable[[list[str]], None]) -> None:
        self._on_remove("tags", callback)

    def add_tags(self, keys: Iterable[str] | str) -> None:
        self._add_keys("tags", keys)

    def remove_tags(self, keys: Iterable[str] | str) -> None:
        self._remove_keys("tags", keys)

    @property
    def uuid(self) -> UUID:
        return UUID(self._uuid)

    @property
    def tags(self) -> set[str]:
        return set(self._get_from_map("tags"))

    @tags.setter
    def tags(self, value: set[str]) -> None:
        tags = {val: True for val in value}
        self._set_in_map("tags", tags)

    @property
    def attributes(self) -> dict[str, Any]:
        return self._get_from_map("attributes")

    @attributes.setter
    def attributes(self, value: dict[str, Any]) -> None:
        self._set_in_map("attributes", value)

    @property
    def author(self) -> str:
        return self._get("author")

    @author.setter
    def author(self, value: str) -> None:
        self._set("author", value)
