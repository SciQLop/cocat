from datetime import datetime
from json import loads

import pytest

from tscat_crdt import DB, EventModel


def test_event():
    db = DB()
    event_model = EventModel(
        start="2025-01-31",
        stop="2026-01-31",
        author="John",
        attributes={"foo": "bar"},
    )

    event = None

    def create_event_callback(_event):
        nonlocal event
        event = _event

    db.on_create_event(create_event_callback)

    assert event == db.create_event(event_model)

    assert loads(repr(event)) == {
        "uuid": str(event_model.uuid),
        "author": "John",
        "products": [],
        "rating": None,
        "start": "2025-01-31 00:00:00",
        "stop": "2026-01-31 00:00:00",
        "tags": [],
        "attributes": {"foo": "bar"},
    }

    assert event.uuid == event_model.uuid

    assert event.start == datetime(2025, 1, 31, 0, 0)
    event.start = "2025-01-30"
    assert event.start == datetime(2025, 1, 30, 0, 0)

    assert event.stop == datetime(2026, 1, 31, 0, 0)
    event.stop = "2026-01-30"
    assert event.stop == datetime(2026, 1, 30, 0, 0)

    assert event.author == "John"
    event.author = "Jeane"
    assert event.author == "Jeane"

    assert event.tags == set()
    event.tags = {"foo", "bar"}
    assert event.tags == {"foo", "bar"}
    event.remove_tags("foo")
    assert event.tags == {"bar"}

    assert event.attributes == {"foo": "bar"}
    event.attributes = {"c": 1}
    assert event.attributes == {"c": 1}
    removed_attributes = []
    set_attributes = []
    event.on_remove_attributes(lambda x: removed_attributes.append(x))
    event.on_set_attributes(lambda x: set_attributes.append(x))
    event.set_attributes(d=2)
    assert event.attributes == {"c": 1, "d": 2}
    assert set_attributes == [{"d": 2}]
    event.remove_attributes({"d"})
    assert removed_attributes == [{"d"}]
    assert event.attributes == {"c": 1}
    event.set_attributes(c=3)
    assert set_attributes == [{"d": 2}, {"c": 3}]
    assert event.attributes == {"c": 3}

    assert event.products == set()
    event.products = {"a", "b"}
    assert event.products == {"a", "b"}
    event.remove_products("a")
    assert event.products == {"b"}
    event.add_products("c")
    assert event.products == {"b", "c"}

    assert event.rating is None
    event.rating = 2
    assert event.rating == 2

    assert event != 0

    values = []

    def callback(value):
        values.append(value)

    event.on_change_start(callback)
    event.start = "2025-01-29"
    event.stop = "2026-01-29"
    event.start = "2025-01-28"

    assert values == [datetime(2025, 1, 29, 0, 0), datetime(2025, 1, 28, 0, 0)]

    values.clear()
    event.on_change_stop(callback)
    event.stop = "2026-01-28"
    assert values == [datetime(2026, 1, 28, 0, 0)]

    values.clear()
    event.on_change_author(callback)
    event.author = "Mike"
    assert values == ["Mike"]

    values.clear()
    event.on_change_rating(callback)
    event.rating = 3
    assert values == [3]

    added_tags = []
    removed_tags = []
    event.on_add_tags(lambda x: added_tags.append(x))
    event.on_remove_tags(lambda x: removed_tags.append(x))
    event.tags = {"baz"}
    assert added_tags == [{"baz"}]
    assert removed_tags == [{"bar"}]

    added_products = []
    removed_products = []
    event.on_add_products(lambda x: added_products.append(x))
    event.on_remove_products(lambda x: removed_products.append(x))
    event.products = {"baz"}
    assert added_products == [{"baz"}]
    assert removed_products == [{"b", "c"}]

    deleted = False

    def delete_callback():
        nonlocal deleted
        deleted = True

    event.on_delete(delete_callback)
    event.delete()

    assert deleted

    with pytest.raises(RuntimeError) as excinfo:
        event.author = "Paul"
    assert str(excinfo.value) == "Event has been deleted"
