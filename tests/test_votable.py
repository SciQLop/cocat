import re
from pathlib import Path

import pytest

from cocat import DB
from cocat.votable import (
    export_votable_file,
    export_votable_str,
    import_votable_file,
    import_votable_str,
)

HERE = Path(__file__).parent


def test_export_different_attributes():
    db = DB()

    event0 = db.create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="Paul",
        attributes={
            "key0": 0,
            "key1": 1,
        },
    )
    event1 = db.create_event(
        start="2027-01-31",
        stop="2028-01-31",
        author="Mike",
        attributes={
            "key1": 2,
            "key2": 3,
        },
    )
    catalogue = db.create_catalogue(
        name="cat",
        author="John",
        attributes={
            "key3": 4,
            "key4": 5,
        },
    )
    catalogue.add_events([event0, event1])

    with pytest.raises(
        ValueError,
        match=re.escape(
            "Export VOTable: not all attributes are present in all events ('key0', 'key2')"
        ),
    ):
        export_votable_str(catalogue)


def test_export_different_attribute_types():
    db = DB()

    event0 = db.create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="Paul",
        attributes={
            "key0": 0,
            "key1": 1,
        },
    )
    event1 = db.create_event(
        start="2027-01-31",
        stop="2028-01-31",
        author="Mike",
        attributes={
            "key0": "foo",
            "key1": "bar",
        },
    )
    catalogue = db.create_catalogue(
        name="cat",
        author="John",
        attributes={
            "key3": 4,
            "key4": 5,
        },
    )
    catalogue.add_events([event0, event1])

    with pytest.raises(
        ValueError,
        match=re.escape(
            "Export VOTable: not all value types are identical for all events for attribute key0"
        ),
    ):
        export_votable_str(catalogue)


def test_export_import(tmp_path):
    votable_path = tmp_path / "votable.xml"
    db = DB()

    event0 = db.create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="Paul",
        attributes={
            "key0": 0,
            "key1": 1,
        },
    )
    event1 = db.create_event(
        start="2027-01-31",
        stop="2028-01-31",
        author="Mike",
        attributes={
            "key0": 2,
            "key1": 3,
        },
    )
    catalogue = db.create_catalogue(
        name="cat",
        author="John",
        attributes={
            "key3": 4,
            "key4": 5,
        },
    )
    catalogue.add_events([event0, event1])

    export_votable_file(catalogue, votable_path)

    db = DB()
    import_votable_file(votable_path, db)

    assert db.events == {event0, event1}
    assert len(db.catalogues) == 1
    assert next(iter(db.catalogues)).name == catalogue.name

    votable_str = export_votable_str(catalogue)

    db = DB()
    import_votable_str(votable_str, db)

    assert db.events == {event0, event1}
    assert len(db.catalogues) == 1
    assert next(iter(db.catalogues)).name == catalogue.name


def test_import_file():
    table = HERE / "data" / "Dst_Li2020.xml"
    db = DB()
    import_votable_file(table, db)

    assert len(db.catalogues) == 1
    catalogue = next(iter(db.catalogues))
    assert catalogue.name == "Dst_Li2020"
    assert len(db.events) == 95
    assert len(catalogue.events) == 95
    assert (
        len(
            [
                event
                for event in catalogue.events
                if event.author == "vincent.genot@irap.omp.eu"
            ]
        )
        == 95
    )


def field_names(xml: str) -> list[list[str]]:
    tables = re.split(r"<TABLE\b", xml)[1:]
    return [re.findall(r'<FIELD[^>]*\bname="([^"]+)"', table) for table in tables]


def test_export_an_empty_catalogue():
    db = DB()
    catalogue = db.create_catalogue(name="empty", author="Paul")

    imported = DB()
    import_votable_str(export_votable_str(catalogue), imported)

    assert [c.name for c in imported.catalogues] == ["empty"]
    assert imported.events == set()


def test_each_catalogue_gets_only_its_own_attribute_columns():
    db = DB()
    event0 = db.create_event(
        start="2025-01-31", stop="2026-01-31", author="Paul", attributes={"key0": 0}
    )
    event1 = db.create_event(
        start="2025-01-31", stop="2026-01-31", author="Paul", attributes={"key1": 1}
    )
    catalogue0 = db.create_catalogue(name="cat0", author="Paul", events=event0)
    catalogue1 = db.create_catalogue(name="cat1", author="Paul", events=event1)

    names0, names1 = field_names(export_votable_str([catalogue0, catalogue1]))

    assert names0[-1] == "key0" and "key1" not in names0
    assert names1[-1] == "key1" and "key0" not in names1
    assert len(names1) == len(set(names1))


START = (
    '<FIELD name="Start Time" ID="TimeIntervalStart" ucd="time.start" '
    'datatype="char" xtype="dateTime" utype="" arraysize="*"/>'
)
STOP = (
    '<FIELD name="Stop Time" ID="TimeIntervalStop" ucd="time.end" '
    'datatype="char" xtype="dateTime" utype="" arraysize="*"/>'
)
ROW = "<TR><TD>2025-01-31T00:00:00</TD><TD>2026-01-31T00:00:00</TD></TR>"


def votable_xml(*tables: str) -> str:
    return (
        '<?xml version="1.0"?><VOTABLE version="1.3" '
        'xmlns="http://www.ivoa.net/xml/VOTable/v1.3"><RESOURCE>'
        + "".join(tables)
        + "</RESOURCE></VOTABLE>"
    )


def table_xml(fields: str, rows: str) -> str:
    return f"<TABLE>{fields}<DATA><TABLEDATA>{rows}</TABLEDATA></DATA></TABLE>"


def test_import_without_author_or_uuid_columns():
    db = DB()
    import_votable_str(votable_xml(table_xml(START + STOP, ROW * 2)), db, "cat")

    (catalogue,) = db.catalogues
    assert catalogue.name == "cat"
    assert {event.author for event in db.events} == {"VOTable Import"}
    assert len(db.events) == 2


def test_import_names_each_table_of_a_multi_table_file():
    db = DB()
    table = table_xml(START + STOP, ROW)
    import_votable_str(votable_xml(table, table), db, "cat")

    assert {catalogue.name for catalogue in db.catalogues} == {"cat_0", "cat_1"}


def test_import_requires_start_and_stop_columns():
    with pytest.raises(ValueError, match="required fields are missing for table cat"):
        import_votable_str(votable_xml(table_xml(START, "")), DB(), "cat")


def test_import_rejects_an_unknown_column_type():
    field = '<FIELD name="count" ID="count" datatype="short"/>'
    with pytest.raises(ValueError, match="cannot import field: count"):
        import_votable_str(votable_xml(table_xml(START + STOP + field, "")), DB())
