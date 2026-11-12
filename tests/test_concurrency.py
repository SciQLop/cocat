"""Two users edit offline at the same time, then their edits merge."""

from pycrdt import Doc

from cocat import DB


def offline_copy(db: DB) -> DB:
    doc: Doc = Doc()
    doc.apply_update(db.doc.get_update())
    return DB(doc=doc)


def merge(db0: DB, db1: DB) -> None:
    update0 = db0.doc.get_update(db1.doc.get_state())
    update1 = db1.doc.get_update(db0.doc.get_state())
    db1.doc.apply_update(update0)
    db0.doc.apply_update(update1)


def test_concurrent_edits_of_one_field_converge():
    db0 = DB()
    event = db0.create_event(start="2025-01-31", stop="2026-01-31", author="Paul")
    db1 = offline_copy(db0)

    event.author = "John"
    db1.get_event(event.uuid).author = "Mike"
    merge(db0, db1)

    assert db0.get_event(event.uuid).author == db1.get_event(event.uuid).author


def test_concurrent_tag_additions_are_both_kept():
    db0 = DB()
    event = db0.create_event(start="2025-01-31", stop="2026-01-31", author="Paul")
    db1 = offline_copy(db0)

    event.add_tags("a")
    db1.get_event(event.uuid).add_tags("b")
    merge(db0, db1)

    assert (
        db0.get_event(event.uuid).tags
        == db1.get_event(event.uuid).tags
        == {
            "a",
            "b",
        }
    )


def test_event_deleted_while_added_to_a_catalogue_elsewhere():
    db0 = DB()
    event = db0.create_event(start="2025-01-31", stop="2026-01-31", author="Paul")
    catalogue = db0.create_catalogue(name="cat", author="Paul")
    db1 = offline_copy(db0)

    event.delete()
    db1.get_catalogue(catalogue.uuid).add_events(db1.get_event(event.uuid))
    merge(db0, db1)

    for db in (db0, db1):
        merged = db.get_catalogue(catalogue.uuid)
        assert list(merged) == []
        assert merged.to_dict()["events"] == []


def test_catalogue_deleted_while_renamed_elsewhere():
    db0 = DB()
    catalogue = db0.create_catalogue(name="cat", author="Paul")
    db1 = offline_copy(db0)

    catalogue.delete()
    db1.get_catalogue(catalogue.uuid).name = "renamed"
    merge(db0, db1)

    assert db0.catalogues == db1.catalogues == set()


def test_listener_ignores_an_event_deleted_elsewhere():
    db0 = DB()
    event = db0.create_event(start="2025-01-31", stop="2026-01-31", author="Paul")
    catalogue = db0.create_catalogue(name="cat", author="Paul")
    db1 = offline_copy(db0)
    added = []
    catalogue.on_add_events(added.append)

    event.delete()
    db1.get_catalogue(catalogue.uuid).add_events(db1.get_event(event.uuid))
    merge(db0, db1)

    assert added == []


def test_dump_and_load_after_an_event_deleted_elsewhere():
    db0 = DB()
    event = db0.create_event(start="2025-01-31", stop="2026-01-31", author="Paul")
    catalogue = db0.create_catalogue(name="cat", author="Paul")
    db1 = offline_copy(db0)

    event.delete()
    db1.get_catalogue(catalogue.uuid).add_events(db1.get_event(event.uuid))
    merge(db0, db1)

    assert DB.from_json(db0.to_json()).catalogues == db0.catalogues
