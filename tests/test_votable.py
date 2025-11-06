import re
from pathlib import Path

import pytest

from cocat import DB
from cocat.votable import export_votable_file, export_votable_str, import_votable_file, import_votable_str

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
        }
    )
    event1 = db.create_event(
        start="2027-01-31",
        stop="2028-01-31",
        author="Mike",
        attributes={
            "key1": 2,
            "key2": 3,
        }
    )
    catalogue = db.create_catalogue(
        name="cat",
        author="John",
        attributes={
            "key3": 4,
            "key4": 5,
        }
    )
    catalogue.add_events([event0, event1])

    with pytest.raises(ValueError, match=re.escape("Export VOTable: not all attributes are present in all events ('key0', 'key2')")):
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
        }
    )
    event1 = db.create_event(
        start="2027-01-31",
        stop="2028-01-31",
        author="Mike",
        attributes={
            "key0": "foo",
            "key1": "bar",
        }
    )
    catalogue = db.create_catalogue(
        name="cat",
        author="John",
        attributes={
            "key3": 4,
            "key4": 5,
        }
    )
    catalogue.add_events([event0, event1])

    with pytest.raises(ValueError, match=re.escape("Export VOTable: not all value types are identical for all events for attribute key0")):
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
        }
    )
    event1 = db.create_event(
        start="2027-01-31",
        stop="2028-01-31",
        author="Mike",
        attributes={
            "key0": 2,
            "key1": 3,
        }
    )
    catalogue = db.create_catalogue(
        name="cat",
        author="John",
        attributes={
            "key3": 4,
            "key4": 5,
        }
    )
    catalogue.add_events([event0, event1])

    export_votable_file(catalogue, votable_path)

    db = DB()
    import_votable_file(votable_path, db)

    assert db.events == {event0, event1}
    assert len(db.catalogues) == 1
    assert list(db.catalogues)[0].name == catalogue.name

    votable_str = export_votable_str(catalogue)

    db = DB()
    import_votable_str(votable_str, db)

    assert db.events == {event0, event1}
    assert len(db.catalogues) == 1
    assert list(db.catalogues)[0].name == catalogue.name


def test_import_file():
    table = HERE / "data" / "Dst_Li2020.xml"
    db = DB()
    import_votable_file(table, db)

    assert len(db.catalogues) == 1
    catalogue = list(db.catalogues)[0]
    assert catalogue.name == "Dst_Li2020"
    assert len(db.events) == 95
    assert len(catalogue.events) == 95
    assert len([event for event in catalogue.events if event.author == "vincent.genot@irap.omp.eu"]) == 95
