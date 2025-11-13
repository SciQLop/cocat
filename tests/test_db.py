from datetime import datetime, timedelta

from pycrdt import Doc

from cocat import DB


def test_create_catalogue():
    db0 = DB()

    assert isinstance(db0.doc, Doc)

    catalogue0 = db0.create_catalogue(
        name="cat0",
        author="John",
    )

    assert db0.catalogues == {catalogue0}

    db1 = DB()
    db1.sync(db0)

    assert db0.catalogues == db1.catalogues == {catalogue0}

    catalogue1 = db1.create_catalogue(
        name="cat1",
        author="Jeane",
    )

    assert db0.catalogues == db1.catalogues == {catalogue0, catalogue1}


def test_create_catalogue_with_events():
    db0 = DB()

    event0 = db0.create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="John",
    )
    catalogue0 = db0.create_catalogue(
        name="cat0",
        author="John",
        events=event0,
    )

    assert db0.catalogues == {catalogue0}
    assert db0.events == {event0}


def test_create_event():
    db0 = DB()
    event0 = db0.create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="John",
    )
    assert db0.events == {event0}

    db1 = DB()
    db1.sync(db0)
    assert db0.events == db1.events == {event0}

    event1 = db1.create_event(
        start="2027-01-31",
        stop="2028-01-31",
        author="Jeane",
    )

    assert db0.events == db1.events == {event0, event1}


def test_add_event():
    db0 = DB()
    db1 = DB()
    db0.sync(db1)
    catalogue = db0.create_catalogue(
        name="cat",
        author="John",
    )
    event = db0.create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="John",
    )
    catalogue.add_events(event)

    assert db0.catalogues == db1.catalogues == {catalogue}
    assert db0.events == db1.events == {event}


def test_sync_both_ways():
    db0 = DB()
    db1 = DB()
    db0.sync(db1)
    db1.sync(db0)


def test_dump_load(tmp_path):
    db0 = DB()
    event = db0.create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="Paul",
    )
    catalogue = db0.create_catalogue(
        name="cat",
        author="John",
    )
    catalogue.add_events(event)
    path0 = tmp_path / "db0.json"
    path0.write_text(db0.to_json())

    db1 = DB.from_json(path0.read_text())
    assert db1.events == {event}
    assert db1.catalogues == {catalogue}
    path1 = tmp_path / "db1.json"
    path1.write_text(db1.to_json())
    assert path0.read_text() == path1.read_text()


def test_db_repr():
    db = DB()

    catalogues = [
        db.create_catalogue(
            uuid=f"d3d76dc2-ac66-4909-b2f2-125990fbe99{i}",
            name="cat0",
            author="John",
            attributes={"foo": "bar"},
        )
        for i in range(10)
    ]

    events = [
        db.create_event(
            uuid=f"7788cbfa-caed-4f05-892e-26e01e25916{i}",
            start=datetime(2025, 1, 1) + timedelta(days=i),
            stop=datetime(2026, 1, 1) + timedelta(days=i),
            author="Paul",
        )
        for i in range(10)
    ]
    for catalogue in catalogues:
        catalogue.add_events(events)
    print(repr(db))
    assert (
        repr(db)
        == """\
{
│   'events': [
│   │   {
│   │   │   'uuid': '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   'start': '2025-01-01 00:00:00',
│   │   │   'stop': '2026-01-01 00:00:00',
│   │   │   'author': 'Paul',
│   │   │   'products': [],
│   │   │   'rating': None,
│   │   │   'tags': [],
│   │   │   'attributes': {}
│   │   },
│   │   {
│   │   │   'uuid': '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   'start': '2025-01-02 00:00:00',
│   │   │   'stop': '2026-01-02 00:00:00',
│   │   │   'author': 'Paul',
│   │   │   'products': [],
│   │   │   'rating': None,
│   │   │   'tags': [],
│   │   │   'attributes': {}
│   │   },
│   │   {
│   │   │   'uuid': '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   'start': '2025-01-03 00:00:00',
│   │   │   'stop': '2026-01-03 00:00:00',
│   │   │   'author': 'Paul',
│   │   │   'products': [],
│   │   │   'rating': None,
│   │   │   'tags': [],
│   │   │   'attributes': {}
│   │   },
│   │   {
│   │   │   'uuid': '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   'start': '2025-01-04 00:00:00',
│   │   │   'stop': '2026-01-04 00:00:00',
│   │   │   'author': 'Paul',
│   │   │   'products': [],
│   │   │   'rating': None,
│   │   │   'tags': [],
│   │   │   'attributes': {}
│   │   },
│   │   {
│   │   │   'uuid': '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   'start': '2025-01-05 00:00:00',
│   │   │   'stop': '2026-01-05 00:00:00',
│   │   │   'author': 'Paul',
│   │   │   'products': [],
│   │   │   'rating': None,
│   │   │   'tags': [],
│   │   │   'attributes': {}
│   │   },
│   │   {
│   │   │   'uuid': '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   'start': '2025-01-06 00:00:00',
│   │   │   'stop': '2026-01-06 00:00:00',
│   │   │   'author': 'Paul',
│   │   │   'products': [],
│   │   │   'rating': None,
│   │   │   'tags': [],
│   │   │   'attributes': {}
│   │   },
│   │   {
│   │   │   'uuid': '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   'start': '2025-01-07 00:00:00',
│   │   │   'stop': '2026-01-07 00:00:00',
│   │   │   'author': 'Paul',
│   │   │   'products': [],
│   │   │   'rating': None,
│   │   │   'tags': [],
│   │   │   'attributes': {}
│   │   },
│   │   {
│   │   │   'uuid': '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   'start': '2025-01-08 00:00:00',
│   │   │   'stop': '2026-01-08 00:00:00',
│   │   │   'author': 'Paul',
│   │   │   'products': [],
│   │   │   'rating': None,
│   │   │   'tags': [],
│   │   │   'attributes': {}
│   │   },
│   │   ... +2
│   ],
│   'catalogues': [
│   │   {
│   │   │   'uuid': 'd3d76dc2-ac66-4909-b2f2-125990fbe990',
│   │   │   'name': 'cat0',
│   │   │   'author': 'John',
│   │   │   'tags': [],
│   │   │   'attributes': {'foo': 'bar'},
│   │   │   'events': [
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   │   ... +2
│   │   │   ]
│   │   },
│   │   {
│   │   │   'uuid': 'd3d76dc2-ac66-4909-b2f2-125990fbe991',
│   │   │   'name': 'cat0',
│   │   │   'author': 'John',
│   │   │   'tags': [],
│   │   │   'attributes': {'foo': 'bar'},
│   │   │   'events': [
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   │   ... +2
│   │   │   ]
│   │   },
│   │   {
│   │   │   'uuid': 'd3d76dc2-ac66-4909-b2f2-125990fbe992',
│   │   │   'name': 'cat0',
│   │   │   'author': 'John',
│   │   │   'tags': [],
│   │   │   'attributes': {'foo': 'bar'},
│   │   │   'events': [
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   │   ... +2
│   │   │   ]
│   │   },
│   │   {
│   │   │   'uuid': 'd3d76dc2-ac66-4909-b2f2-125990fbe993',
│   │   │   'name': 'cat0',
│   │   │   'author': 'John',
│   │   │   'tags': [],
│   │   │   'attributes': {'foo': 'bar'},
│   │   │   'events': [
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   │   ... +2
│   │   │   ]
│   │   },
│   │   {
│   │   │   'uuid': 'd3d76dc2-ac66-4909-b2f2-125990fbe994',
│   │   │   'name': 'cat0',
│   │   │   'author': 'John',
│   │   │   'tags': [],
│   │   │   'attributes': {'foo': 'bar'},
│   │   │   'events': [
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   │   ... +2
│   │   │   ]
│   │   },
│   │   {
│   │   │   'uuid': 'd3d76dc2-ac66-4909-b2f2-125990fbe995',
│   │   │   'name': 'cat0',
│   │   │   'author': 'John',
│   │   │   'tags': [],
│   │   │   'attributes': {'foo': 'bar'},
│   │   │   'events': [
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   │   ... +2
│   │   │   ]
│   │   },
│   │   {
│   │   │   'uuid': 'd3d76dc2-ac66-4909-b2f2-125990fbe996',
│   │   │   'name': 'cat0',
│   │   │   'author': 'John',
│   │   │   'tags': [],
│   │   │   'attributes': {'foo': 'bar'},
│   │   │   'events': [
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   │   ... +2
│   │   │   ]
│   │   },
│   │   {
│   │   │   'uuid': 'd3d76dc2-ac66-4909-b2f2-125990fbe997',
│   │   │   'name': 'cat0',
│   │   │   'author': 'John',
│   │   │   'tags': [],
│   │   │   'attributes': {'foo': 'bar'},
│   │   │   'events': [
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259160',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259161',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259162',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259163',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259164',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259165',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259166',
│   │   │   │   '7788cbfa-caed-4f05-892e-26e01e259167',
│   │   │   │   ... +2
│   │   │   ]
│   │   },
│   │   ... +2
│   ]
}
"""
    )
