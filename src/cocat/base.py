from collections.abc import Callable, Iterable
from typing import Any, TYPE_CHECKING, cast
from uuid import UUID

from pycrdt import Map

if TYPE_CHECKING:
    from .db import DB

class Mixin:
    _uuid: str
    _map: Map
    _db: "DB"
    _get: Callable[[str], Any]
    _set: Callable[[str, Any], None]
    _check_deleted: Callable[[], None]
    _on_add: Callable[[str, Callable[[Any], None]], None]
    _on_remove: Callable[[str, Callable[[list[str]], None]], None]

    def _callback(self, callback: Callable[..., None], origin: Any, *args: Any) -> None:
        if origin is not self:
            callback(*args)

    def _get_from_map(self, field: str) -> dict[str, Any]:
        with self._db.transaction():
            self._check_deleted()
            map = cast(Map, self._map[field])
            res = map.to_py()
            assert res is not None
            return res

    def _set_in_map(self, field: str, value: dict[str, Any]) -> None:
        with self._db.transaction():
            self._check_deleted()
            map = cast(Map, self._map[field])
            map.clear()
            map.update(value)

    def _add_keys(self, field: str, keys: Iterable[str] | str) -> None:
        with self._db.transaction():
            key_list = [keys] if isinstance(keys, str) else keys
            self._check_deleted()
            map = cast(Map, self._map[field])
            for key in key_list:
                map[key] = True

    def _add_items(self, field: str, items: dict[str, Any]) -> None:
        with self._db.transaction():
            self._check_deleted()
            map = cast(Map, self._map[field])
            map.update(items)

    def _remove_keys(self, field: str, keys: Iterable[str] | str) -> None:
        with self._db.transaction():
            key_list = [keys] if isinstance(keys, str) else keys
            self._check_deleted()
            map = cast(Map, self._map[field])
            for key in key_list:
                del map[key]

    def on_set_attributes(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """
        Registers a callback to be called when attributes are set.

        Args:
            callback: The callback to call with a dictionary of attribute items that were set.
        """
        self._on_add("attributes", callback)

    def on_remove_attributes(self, callback: Callable[[list[str]], None]) -> None:
        """
        Registers a callback to be called when attributes are removed.

        Args:
            callback: The callback to call with a list of attribute keys that were removed.
        """
        self._on_remove("attributes", callback)

    def set_attributes(self, **kwargs: Any) -> None:
        """
        Sets attributes.

        Args:
            kwargs: The attributes to set.
        """
        self._add_items("attributes", kwargs)

    def remove_attributes(self, keys: Iterable[str] | str) -> None:
        """
        Removes attributes.

        Args:
            keys: The attribute keys to remove.
        """
        self._remove_keys("attributes", keys)

    def on_add_tags(self, callback: Callable[[set[str]], None]) -> None:
        """
        Registers a callback to be called when tags are added.

        Args:
            callback: The callback to call with the set of added tags.
        """

        def _callback(values: dict[str, Any]) -> None:
            callback(set(values))

        self._on_add("tags", _callback)

    def on_remove_tags(self, callback: Callable[[list[str]], None]) -> None:
        """
        Registers a callback to be called when tags are removed:

        Args:
            callback: The callback to call with the list of removed tags.
        """
        self._on_remove("tags", callback)

    def add_tags(self, keys: Iterable[str] | str) -> None:
        """
        Adds tags.

        Args:
            keys: The tags to add.
        """
        self._add_keys("tags", keys)

    def remove_tags(self, keys: Iterable[str] | str) -> None:
        """
        Removes tags.

        Args:
            keys: The tags to remove.
        """
        self._remove_keys("tags", keys)

    @property
    def db(self) -> "DB":
        """
        Returns:
            The [database][cocat.DB] it belongs to.
        """
        return self._db

    @property
    def uuid(self) -> UUID:
        """
        Returns:
            The UUID.
        """
        return UUID(self._uuid)

    @property
    def tags(self) -> set[str]:
        """
        Returns:
            The tags.
        """
        return set(self._get_from_map("tags"))

    @tags.setter
    def tags(self, value: set[str]) -> None:
        """
        Args:
            value: The tags to set.
        """
        tags = {val: True for val in value}
        self._set_in_map("tags", tags)

    @property
    def attributes(self) -> dict[str, Any]:
        """
        Returns:
            The attributes.
        """
        return self._get_from_map("attributes")

    @attributes.setter
    def attributes(self, value: dict[str, Any]) -> None:
        """
        Args:
            value: The attributes to set.
        """
        self._set_in_map("attributes", value)

    @property
    def author(self) -> str:
        """
        Returns:
            The author.
        """
        return self._get("author")

    @author.setter
    def author(self, value: str) -> None:
        """
        Args:
            value: The author to set.
        """
        self._set("author", value)
