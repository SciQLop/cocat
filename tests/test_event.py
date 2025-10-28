from datetime import datetime
from json import loads

import pytest

from cocat import DB


def test_event():
    db0 = DB()
    db1 = DB()
    db1.sync(db0)

    event1 = None

    def create_event_callback(_event):
        nonlocal event1
        event1 = _event

    db0.on_create_event(lambda: None)  # should not be called
    db1.on_create_event(create_event_callback)

    event0 = db0.create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="John",
        attributes={"foo": "bar"},
        rating=3,
    )
    assert event1 == event0

    assert loads(repr(event1)) == {
        "uuid": str(event0.uuid),
        "author": "John",
        "products": [],
        "rating": 3,
        "start": "2025-01-31 00:00:00",
        "stop": "2026-01-31 00:00:00",
        "tags": [],
        "attributes": {"foo": "bar"},
    }

    assert event1.uuid == event0.uuid

    assert event1.start == datetime(2025, 1, 31, 0, 0)
    event0.start = "2025-01-30"
    assert event1.start == datetime(2025, 1, 30, 0, 0)

    assert event1.stop == datetime(2026, 1, 31, 0, 0)
    event0.stop = "2026-01-30"
    assert event1.stop == datetime(2026, 1, 30, 0, 0)

    assert event1.author == "John"
    event0.author = "Jeane"
    assert event1.author == "Jeane"

    assert event1.tags == set()
    event0.tags = {"foo", "bar"}
    assert event1.tags == {"foo", "bar"}
    event0.remove_tags("foo")
    assert event1.tags == {"bar"}

    assert event1.attributes == {"foo": "bar"}
    event0.attributes = {"c": 1}
    assert event1.attributes == {"c": 1}
    removed_attributes = []
    set_attributes = []
    event1.on_remove_attributes(lambda x: removed_attributes.append(x))
    event1.on_set_attributes(lambda x: set_attributes.append(x))
    event0.set_attributes(d=2)
    assert event1.attributes == {"c": 1, "d": 2}
    assert set_attributes == [{"d": 2}]
    event0.remove_attributes({"d"})
    assert removed_attributes == [{"d"}]
    assert event1.attributes == {"c": 1}
    event0.set_attributes(c=3)
    assert set_attributes == [{"d": 2}, {"c": 3}]
    assert event1.attributes == {"c": 3}

    assert event1.products == set()
    event0.products = {"a", "b"}
    assert event1.products == {"a", "b"}
    event0.remove_products("a")
    assert event1.products == {"b"}
    event0.add_products("c")
    assert event1.products == {"b", "c"}

    assert event1.rating == 3
    event0.rating = 2
    assert event1.rating == 2

    assert event1 != 0

    values = []

    def callback(value):
        values.append(value)

    event1.on_change_start(callback)
    event0.start = "2025-01-29"
    event0.stop = "2026-01-29"
    event0.start = "2025-01-28"

    assert values == [datetime(2025, 1, 29, 0, 0), datetime(2025, 1, 28, 0, 0)]

    values.clear()
    event1.on_change_stop(callback)
    event0.stop = "2026-01-28"
    assert values == [datetime(2026, 1, 28, 0, 0)]

    values.clear()
    event1.on_change_author(callback)
    event0.author = "Mike"
    assert values == ["Mike"]

    values.clear()
    event1.on_change_rating(callback)
    event0.rating = 3
    assert values == [3]

    added_tags = []
    removed_tags = []
    event1.on_add_tags(lambda x: added_tags.append(x))
    event1.on_remove_tags(lambda x: removed_tags.append(x))
    event0.tags = {"baz"}
    assert added_tags == [{"baz"}]
    assert removed_tags == [{"bar"}]

    added_products = []
    removed_products = []
    event1.on_add_products(lambda x: added_products.append(x))
    event1.on_remove_products(lambda x: removed_products.append(x))
    event0.products = {"baz"}
    assert added_products == [{"baz"}]
    assert removed_products == [{"b", "c"}]

    deleted = False

    def delete_callback():
        nonlocal deleted
        deleted = True

    event1.on_delete(delete_callback)
    event0.delete()

    assert deleted

    with pytest.raises(RuntimeError) as excinfo:
        event0.author = "Paul"
    assert str(excinfo.value) == "Event has been deleted"
