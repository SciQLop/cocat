from json import loads

import pytest

from cocat import DB, CatalogueModel, EventModel


def test_catalogue():
    db0 = DB()
    db1 = DB()
    db1.sync(db0)

    catalogue_model = CatalogueModel(
        name="cat0",
        author="John",
        attributes={"foo": "bar"}
    )

    catalogue1 = None

    def create_catalogue_callback(_catalogue):
        nonlocal catalogue1
        catalogue1 = _catalogue

    db0.on_create_catalogue(lambda: None)  # should not be called
    db1.on_create_catalogue(create_catalogue_callback)

    catalogue0 = db0.create_catalogue(catalogue_model)
    assert catalogue1 is not catalogue0
    assert catalogue1 == catalogue0

    event_model = EventModel(
        start="2025-01-31",
        stop="2026-01-31",
        author="John",
    )
    event0 = db0.create_event(event_model)
    catalogue0.add_events(event0)

    assert loads(repr(catalogue0)) == {
        "uuid": str(catalogue_model.uuid),
        "events": [str(event_model.uuid)],
        "author": "John",
        "name": "cat0",
        "tags": [],
        "attributes": {"foo": "bar"},
    }

    assert catalogue0.uuid == catalogue_model.uuid

    assert catalogue0.name == "cat0"
    catalogue0.name = "cat1"
    assert catalogue0.name == "cat1"

    assert catalogue0.author == "John"
    catalogue0.author = "Jeane"
    assert catalogue0.author == "Jeane"

    assert catalogue0.tags == set()
    added_tags = []
    catalogue1.on_add_tags(lambda x: added_tags.append(x))
    catalogue0.tags = {"foo", "bar"}
    assert added_tags == [{"foo", "bar"}]
    assert catalogue1.tags == {"foo", "bar"}
    removed_tags = []
    catalogue1.on_remove_tags(lambda x: removed_tags.append(x))
    catalogue0.remove_tags("foo")
    assert catalogue1.tags == {"bar"}
    assert removed_tags == [{"foo"}]
    catalogue0.add_tags("baz")
    assert catalogue1.tags == {"bar", "baz"}
    assert added_tags == [{"foo", "bar"}, {"baz"}]

    assert catalogue1.attributes == {"foo": "bar"}
    catalogue0.attributes = {"c": 1}
    assert catalogue1.attributes == {"c": 1}
    removed_attributes = []
    set_attributes = []
    catalogue1.on_remove_attributes(lambda x: removed_attributes.append(x))
    catalogue1.on_set_attributes(lambda x: set_attributes.append(x))
    catalogue0.set_attributes(d=2)
    assert catalogue1.attributes == {"c": 1, "d": 2}
    assert set_attributes == [{"d": 2}]
    catalogue0.remove_attributes({"d"})
    assert removed_attributes == [{"d"}]
    assert catalogue1.attributes == {"c": 1}
    catalogue0.set_attributes(c=3)
    assert set_attributes == [{"d": 2}, {"c": 3}]
    assert catalogue1.attributes == {"c": 3}

    event1 = db0.create_event(EventModel(
        start="2027-01-31",
        stop="2028-01-31",
        author="Jeane",
    ))
    assert catalogue1.events == {event0}
    catalogue0.events = {event1}
    assert catalogue1.events == {event1}

    assert catalogue0 != 0

    values = []

    def callback(value):
        values.append(value)

    catalogue1.on_change_name(callback)
    catalogue0.name = "cat1"
    assert values == ["cat1"]

    values.clear()
    catalogue1.on_change_author(callback)
    catalogue0.author = "Mike"
    assert values == ["Mike"]

    added_events = []
    removed_events = []
    catalogue1.on_add_events(lambda events: added_events.append(events))
    catalogue1.on_remove_events(lambda events: removed_events.append(events))
    event2 = db0.create_event(EventModel(
        start="2029-01-31",
        stop="2030-01-31",
        author="Mike",
    ))
    catalogue0.events = {event0, event2}
    assert removed_events == [{str(event1.uuid)}]
    assert added_events == [{event0, event2}]

    removed_events.clear()
    catalogue0.remove_events(event0)
    assert catalogue1.events == {event2}
    assert removed_events == [{str(event0.uuid)}]

    event2.delete()
    assert catalogue1.events == set()

    catalogue_deleted = False

    def delete_callback():
        nonlocal catalogue_deleted
        catalogue_deleted = True

    catalogue1.on_delete(delete_callback)
    catalogue0.delete()

    assert catalogue_deleted

    with pytest.raises(RuntimeError) as excinfo:
        catalogue0.name = "cat2"
    assert str(excinfo.value) == "Catalogue has been deleted"
