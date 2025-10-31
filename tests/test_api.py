import pytest

from httpx_ws import WebSocketUpgradeError

from cocat import (
    create_catalogue,
    create_event,
    load_catalogue,
    load_event,
    log_in,
    log_out,
    save_catalogue,
    save_event,
    set_config,
)


pytestmark = pytest.mark.anyio

async def test_api(tmp_path, anyio_backend, server, user):
    host, port = server
    file_path = tmp_path / "updates.y"
    set_config(
        host=f"http://{host}",
        port=port,
        file_path=file_path,
        room_id="room1",
    )
    log_in(*user)

    catalogue0 = create_catalogue(name="cat0", author="Paul")
    catalogue1 = create_catalogue(name="cat1", author="Mike")

    if anyio_backend == "trio":
        with pytest.raises(RuntimeError, match="no running event loop"):
            await load_catalogue("cat0")

        return
    else:
        with pytest.raises(RuntimeError, match="No catalogue found with name or UUID: cat0"):
            await load_catalogue("cat0")

    await save_catalogue(catalogue0)
    await save_catalogue("cat1")
    assert catalogue0 == await load_catalogue("cat0")
    assert catalogue1 == await load_catalogue("cat1")

    event0 = create_event(
        start="2025-01-31",
        stop="2026-01-31",
        author="John",
    )
    event1 = create_event(
        start="2027-01-31",
        stop="2028-01-31",
        author="Alyson",
    )

    with pytest.raises(RuntimeError, match=f"No event found with UUID: {event0.uuid}"):
        await load_event(event0.uuid)

    await save_event(event0)
    await save_event(event1.uuid)
    assert event0 == await load_event(event0.uuid)
    assert event1 == await load_event(event1.uuid)

    log_out()

    with pytest.RaisesGroup(WebSocketUpgradeError):
        await load_catalogue("cat2")


async def test_login(tmp_path, server, anyio_backend):
    if anyio_backend == "trio":
        pytest.skip("Doesn't work on Trio")

    host, port = server
    file_path = tmp_path / "updates.y"
    set_config(
        host=f"http://{host}",
        port=port,
        file_path=file_path,
        room_id="room1",
    )

    with pytest.RaisesGroup(WebSocketUpgradeError):
        await load_catalogue("cat0")
