import pytest
from anyio import fail_after, sleep

from tscat_crdt import DB, CatalogueModel, EventModel, File
from wiredb import bind, connect


pytestmark = pytest.mark.anyio

async def test_websocket(free_tcp_port, tmp_path):
    update_path = tmp_path / "updates.y"
    async with bind("websocket", host="localhost", port=free_tcp_port):
        async with (
            connect("websocket", host="http://localhost", port=free_tcp_port) as client0,
            connect("websocket", host="http://localhost", port=free_tcp_port) as client1,
            File(update_path, client0.doc),
        ):
            db0 = DB(doc=client0.doc)
            db1 = DB(doc=client1.doc)

            async with db0.doc.transaction():
                event0 = db0.create_event(EventModel(
                    start="2025-01-31",
                    stop="2026-01-31",
                    author="Paul",
                ))
                catalogue0 = db0.create_catalogue(CatalogueModel(
                    name="cat",
                    author="John",
                ))
                catalogue0.add_events(event0)

            with fail_after(1):
                while True:
                    await sleep(0.01)
                    if db1.events and db1.catalogues:
                        assert db1.events == {event0}
                        assert db1.catalogues == {catalogue0}
                        break

            async with db1.doc.transaction():
                event1 = db1.create_event(EventModel(
                    start="2027-01-31",
                    stop="2028-01-31",
                    author="Mike",
                ))
                catalogue1 = db1.get_catalogue(str(catalogue0.uuid))
                catalogue1.add_events(event1)

            with fail_after(1):
                while True:
                    await sleep(0.01)
                    if len(db0.events) > 1:
                        assert db0.events == {event0, event1}
                        assert db0.catalogues == {catalogue1}
                        break

    db2 = DB()
    async with File(update_path, db2.doc):
        pass
    assert db2.events == {event0, event1}
    assert db2.catalogues == {catalogue1}
