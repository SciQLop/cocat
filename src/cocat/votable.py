import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from .catalogue import Catalogue
from .db import DB, Event

if TYPE_CHECKING:
    from astropy.io.votable.tree import Field as VOField  # type: ignore[import-untyped]
    from astropy.io.votable.tree import (  # type: ignore[import-untyped]
        Table,
        VOTableFile,
    )


@dataclass
class _VOTableCocatField:
    python_type: type
    attr: dict[str, str]
    convert_vot: Callable[[Any], Any]
    convert_cocat: Callable[[Any], Any]
    cocat_name: str | None = None

    def name(self, field: "VOField") -> str:
        if self.cocat_name:
            return self.cocat_name
        return field.name

    def match(self, field: "VOField") -> bool:
        for k, v in self.attr.items():
            if field.__getattribute__(k) != v:
                return False
        return True

    def make_vot_field(self, table: "Table", name: str) -> "VOField":
        from astropy.io.votable.tree import Field as VOField

        if "name" not in self.attr:
            return VOField(table, name=name, **self.attr)
        return VOField(table, **self.attr)


class _VOTableCocatFieldSpecialDateTime(_VOTableCocatField):
    def __init__(self, attrs: dict[str, str], cocat_name: str | None = None) -> None:
        attrs.update(
            {"datatype": "char", "xtype": "dateTime", "utype": "", "arraysize": "*"}
        )
        super().__init__(datetime, attrs, datetime.isoformat, str, cocat_name)


def _vo_table_field_from(arg: type | str) -> _VOTableCocatField:
    vtf: _VOTableCocatField | None = None
    if isinstance(arg, str):
        for vtf in VOTABLE_COCAT_FIELDS:
            if vtf.cocat_name == arg:
                break
    else:
        for vtf in VOTABLE_COCAT_FIELDS:
            if vtf.cocat_name is None and vtf.python_type is arg:
                break

    assert vtf is not None
    return vtf


VOTABLE_COCAT_FIELDS = [
    _VOTableCocatFieldSpecialDateTime(
        {"name": "Start Time", "ID": "TimeIntervalStart", "ucd": "time.start"}, "start"
    ),
    _VOTableCocatFieldSpecialDateTime(
        {"name": "Stop Time", "ID": "TimeIntervalStop", "ucd": "time.end"}, "stop"
    ),
    _VOTableCocatFieldSpecialDateTime({}),
    _VOTableCocatField(
        int,
        {"datatype": "long"},
        lambda x: 0 if x is None else x,
        lambda x: None if x == 0 else x,
        "rating",
    ),
    _VOTableCocatField(int, {"datatype": "long"}, int, int),
    _VOTableCocatField(float, {"datatype": "double"}, float, float),
    _VOTableCocatField(bool, {"datatype": "boolean"}, bool, bool),
    _VOTableCocatField(
        list,
        {"datatype": "char", "arraysize": "*", "utype": "json"},
        json.dumps,
        json.loads,
    ),
    _VOTableCocatField(
        list,
        {"datatype": "char", "arraysize": "*", "name": "products"},
        json.dumps,
        json.loads,
        "products",
    ),
    _VOTableCocatField(
        list,
        {"datatype": "char", "arraysize": "*", "name": "tags"},
        json.dumps,
        json.loads,
        "tags",
    ),
    _VOTableCocatField(
        str, {"datatype": "char", "arraysize": "*"}, str, str
    ),  # last item, catch all strings
]

ATTRIBUTES = [
    ("start", _vo_table_field_from("start")),
    ("stop", _vo_table_field_from("stop")),
    ("author", _vo_table_field_from(str)),
    ("uuid", _vo_table_field_from(str)),
    ("tags", _vo_table_field_from(list)),
    ("products", _vo_table_field_from(list)),
    ("rating", _vo_table_field_from("rating")),
]

STANDARD_FIELDS = [v[0] for v in ATTRIBUTES]


def export_votable(catalogues: Sequence[Catalogue] | Catalogue) -> "VOTableFile":
    from astropy.io.votable.tree import Resource, VOTableFile

    catalogue_list = (
        [catalogues] if isinstance(catalogues, Catalogue) else list(catalogues)
    )
    votable = VOTableFile()
    if len(catalogue_list) == 1:
        catalogue = catalogue_list[0]
        votable.description = f"Contact:{catalogue.author};Name:{catalogue.name}"

    resource = Resource()
    votable.resources.append(resource)
    resource.tables.extend(
        _catalogue_table(votable, catalogue) for catalogue in catalogue_list
    )
    return votable


def _catalogue_table(votable: "VOTableFile", catalogue: Catalogue) -> "Table":
    from astropy.io.votable.tree import TableElement

    events = list(catalogue)
    columns = ATTRIBUTES + _attribute_columns(events)
    table = TableElement(votable, name=catalogue.name.replace(" ", "_"))
    table.fields.extend([vtf.make_vot_field(votable, name) for name, vtf in columns])
    table.create_arrays(len(events))
    for i, event in enumerate(events):
        table.array[i] = tuple(
            vtf.convert_vot(_event_value(event, name)) for name, vtf in columns
        )
    return table


def _attribute_columns(events: list[Event]) -> list[tuple[str, _VOTableCocatField]]:
    names = [set(event.attributes) for event in events]
    all_names = set().union(*names)
    missing = all_names - all_names.intersection(*names)
    if missing:
        raise ValueError(
            "Export VOTable: not all attributes are present in all events "
            + f"{tuple(sorted(missing))}"
        )
    return [(name, _attribute_field(events, name)) for name in sorted(all_names)]


def _attribute_field(events: list[Event], name: str) -> _VOTableCocatField:
    value_types = {type(event.attributes[name]) for event in events}
    if len(value_types) != 1:
        raise ValueError(
            "Export VOTable: not all value types are "
            + f"identical for all events for attribute {name}"
        )
    return _vo_table_field_from(value_types.pop())


def _event_value(event: Event, name: str) -> Any:
    if name not in STANDARD_FIELDS:
        return event.attributes[name]
    value = getattr(event, name)
    return sorted(value) if isinstance(value, set) else value


REQUIRED_FIELD_NAMES = {"Start Time", "Stop Time"}

Column = tuple[int, str, _VOTableCocatField]


def import_votable(
    votable: "VOTableFile", db: DB, table_name: str | None = None
) -> None:
    author, name = _description(votable, table_name)
    tables = list(votable.iter_tables())
    events: dict[str, dict[str, Any]] = {}
    catalogues: dict[str, list[str]] = {}
    for i, table in enumerate(tables):
        this_name = name if len(tables) == 1 else f"{name}_{i}"
        columns = _table_columns(table, this_name)
        rows = [_event_from_row(row, columns, author) for row in table.array]
        for event in rows:
            events.setdefault(event["uuid"], event)
        catalogues[this_name] = [event["uuid"] for event in rows]

    with db.transaction():
        for event in events.values():
            db.create_event(**event)
        for this_name, uuids in catalogues.items():
            catalogue = db.create_catalogue(name=this_name, author=author)
            catalogue.add_events([Event._from_uuid(uuid, db) for uuid in uuids])


def _description(votable: "VOTableFile", table_name: str | None) -> tuple[str, str]:
    """The author and catalogue name, from a "Contact:...;Name:..." description."""
    entries = dict(
        line.strip().split(":", 1)
        for line in str(votable.description or "").split(";")
        if ":" in line
    )
    author = entries.get("Contact", "VOTable Import").strip()
    default_name = table_name or f"Imported Catalogue from {datetime.now()}"
    return author, entries.get("Name", default_name).strip()


def _table_columns(table: "Table", name: str) -> list[Column]:
    if not REQUIRED_FIELD_NAMES <= {field.name for field in table.fields}:
        raise ValueError(
            f"VOTable import: required fields are missing for table {name}"
        )
    columns = []
    for index, field in enumerate(table.fields):
        vtf = _matching_field(field)
        columns.append((index, vtf.name(field), vtf))
    return columns


def _matching_field(field: "VOField") -> _VOTableCocatField:
    for vtf in VOTABLE_COCAT_FIELDS:
        if vtf.match(field):
            return vtf
    raise ValueError(
        f"VOTable import: cannot import field: {field.ID}, {field.name}, "
        + f"{field.datatype}, {field.xtype}"
    )


def _event_from_row(row: Any, columns: list[Column], author: str) -> dict[str, Any]:
    event: dict[str, Any] = {"author": author, "uuid": str(uuid4()), "attributes": {}}
    for index, name, vtf in columns:
        value = vtf.convert_cocat(row[index])
        if name in STANDARD_FIELDS:
            event[name] = value
        else:
            event["attributes"][name] = value
    return event


def import_votable_file(
    file_path: str | Path, db: DB, table_name: str | None = None
) -> None:
    """
    Imports a VOTable file into a database.

    Args:
        file_path: The VOTable file path.
        db: The database into which to import the VOTable.
    """
    from astropy.io.votable import parse  # type: ignore[import-untyped]

    import_votable(parse(file_path), db, table_name=table_name)


def import_votable_str(xml_content: str, db: DB, table_name: str | None = None) -> None:
    """
    Imports a VOTable XML string into a database.

    Args:
        xml_content: The VOTable content as an XML string.
        db: The database into which to import the VOTable.
    """
    from astropy.io.votable import parse  # type: ignore[import-untyped]

    import_votable(parse(BytesIO(xml_content.encode())), db, table_name=table_name)


def export_votable_file(
    catalogues: Sequence[Catalogue] | Catalogue, file_path: str | Path
) -> None:
    """
    Exports catalogues to a VOTable file.

    Args:
        catalogues: The catalogue(s) to export.
        file_path: The path to the exported file.
    """
    with open(file_path, "wb") as f:
        export_votable(catalogues).to_xml(f)


def export_votable_str(catalogues: Sequence[Catalogue] | Catalogue) -> str:
    """
    Exports catalogues as a VOTable XML string.

    Args:
        catalogues: The catalogue(s) to export.

    Returns:
        The VOTable as an XML string.
    """
    content = BytesIO()
    export_votable(catalogues).to_xml(content)
    return content.getvalue().decode()
