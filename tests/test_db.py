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
