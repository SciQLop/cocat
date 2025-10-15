from json import loads

import pytest

from tscat_crdt import DB, CatalogueModel, EventModel


def test_catalogue():
    db = DB()
    catalogue_model = CatalogueModel(
        name="cat0",
        author="John",
        attributes={"foo": "bar"}
    )

    catalogue = None

    def create_catalogue_callback(_catalogue):
        nonlocal catalogue
        catalogue = _catalogue

    db.on_create_catalogue(create_catalogue_callback)

    assert catalogue == db.create_catalogue(catalogue_model)

    event_model = EventModel(
        start="2025-01-31",
        stop="2026-01-31",
        author="John",
    )
    event0 = db.create_event(event_model)
    catalogue.add_events(event0)

    assert loads(repr(catalogue)) == {
        "uuid": str(catalogue_model.uuid),
        "events": [str(event_model.uuid)],
        "author": "John",
        "name": "cat0",
        "tags": [],
        "attributes": {"foo": "bar"},
    }

    assert catalogue.uuid == catalogue_model.uuid

    assert catalogue.name == "cat0"
    catalogue.name = "cat1"
    assert catalogue.name == "cat1"

    assert catalogue.author == "John"
    catalogue.author = "Jeane"
    assert catalogue.author == "Jeane"

    assert catalogue.tags == set()
    added_tags = []
    catalogue.on_add_tags(lambda x: added_tags.append(x))
    catalogue.tags = {"foo", "bar"}
    assert added_tags == [{"foo", "bar"}]
    assert catalogue.tags == {"foo", "bar"}
    removed_tags = []
    catalogue.on_remove_tags(lambda x: removed_tags.append(x))
    catalogue.remove_tags("foo")
    assert catalogue.tags == {"bar"}
    assert removed_tags == [{"foo"}]
    catalogue.add_tags("baz")
    assert catalogue.tags == {"bar", "baz"}
    assert added_tags == [{"foo", "bar"}, {"baz"}]

    assert catalogue.attributes == {"foo": "bar"}
    catalogue.attributes = {"c": 1}
    assert catalogue.attributes == {"c": 1}
    removed_attributes = []
    set_attributes = []
    catalogue.on_remove_attributes(lambda x: removed_attributes.append(x))
    catalogue.on_set_attributes(lambda x: set_attributes.append(x))
    catalogue.set_attributes(d=2)
    assert catalogue.attributes == {"c": 1, "d": 2}
    assert set_attributes == [{"d": 2}]
    catalogue.remove_attributes({"d"})
    assert removed_attributes == [{"d"}]
    assert catalogue.attributes == {"c": 1}
    catalogue.set_attributes(c=3)
    assert set_attributes == [{"d": 2}, {"c": 3}]
    assert catalogue.attributes == {"c": 3}

    event1 = db.create_event(EventModel(
        start="2027-01-31",
        stop="2028-01-31",
        author="Jeane",
    ))
    assert catalogue.events == {event0}
    catalogue.events = {event1}
    assert catalogue.events == {event1}

    assert catalogue != 0

    values = []

    def callback(value):
        values.append(value)

    catalogue.on_change_name(callback)
    catalogue.name = "cat1"
    assert values == ["cat1"]

    values.clear()
    catalogue.on_change_author(callback)
    catalogue.author = "Mike"
    assert values == ["Mike"]

    added_events = []
    removed_events = []
    catalogue.on_add_events(lambda events: added_events.append(events))
    catalogue.on_remove_events(lambda events: removed_events.append(events))
    event2 = db.create_event(EventModel(
        start="2029-01-31",
        stop="2030-01-31",
        author="Mike",
    ))
    catalogue.events = {event0, event2}
    assert removed_events == [{str(event1.uuid)}]
    assert added_events == [{event0, event2}]

    removed_events.clear()
    catalogue.remove_events(event0)
    assert catalogue.events == {event2}
    assert removed_events == [{str(event0.uuid)}]

    event2.delete()
    assert catalogue.events == set()

    catalogue_deleted = False

    def delete_callback():
        nonlocal catalogue_deleted
        catalogue_deleted = True

    catalogue.on_delete(delete_callback)
    catalogue.delete()

    assert catalogue_deleted

    with pytest.raises(RuntimeError) as excinfo:
        catalogue.name = "cat2"
    assert str(excinfo.value) == "Catalogue has been deleted"
