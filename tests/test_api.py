import os
import platform
import signal

import httpx
import pexpect  # type: ignore[import-untyped]
import pytest
from anyio import fail_after, sleep
from httpx_ws import WebSocketUpgradeError
from wiredb import connect

from cocat import (
    DB,
    create_catalogue,
    create_event,
    get_catalogue,
    get_event,
    log_in,
    log_out,
    refresh,
    save,
    set_config,
    synchronize,
    wait_connected,
)
from cocat import (
    connect as _connect,
)

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_api(tmp_path, anyio_backend, server, user):
    host, port = server
    username, password = user
    data = {"username": username, "password": password}
    response = httpx.post(f"http://{host}:{port}/auth/jwt/login", data=data)
    cookie = response.cookies.get("fastapiusersauth")
    cookies = httpx.Cookies()
    cookies.set("fastapiusersauth", cookie)
    async with connect(
        "websocket", id="room/room1", host=f"http://{host}", port=port, cookies=cookies
    ) as client:
        db = DB(doc=client.doc)

        file_path = tmp_path / "updates.y"
        set_config(
            host=f"http://{host}",
            port=port,
            file_path=file_path,
            room_id="room1",
        )
        log_in(*user)
        await synchronize()

        catalogue0 = create_catalogue(name="cat0", author="Paul")
        event0 = create_event(
            start="2025-01-30",
            stop="2026-01-30",
            author="Mike",
        )
        assert event0 == get_event(event0.uuid)
        assert catalogue0 == get_catalogue(catalogue0.uuid)

        save()

        with fail_after(1):
            while True:
                try:
                    catalogue1 = db.get_catalogue("cat0")
                    assert catalogue0 == catalogue1
                    break
                except Exception as exc:
                    if not str(exc).startswith("No catalogue found"):
                        raise  # pragma: nocover
                await sleep(0.1)

        event1 = db.create_event(
            start="2025-01-31",
            stop="2026-01-31",
            author="John",
        )

        with fail_after(1):
            while True:
                try:
                    event0 = get_event(event1.uuid)
                    assert event0 == event1
                    break
                except Exception as exc:
                    if not str(exc).startswith("No event found"):
                        raise  # pragma: nocover
                await sleep(0.1)
                refresh()

    log_out()

    with pytest.RaisesGroup(WebSocketUpgradeError):
        _connect()
        await wait_connected()


@pytest.mark.parametrize("anyio_backend", ["asyncio"])
async def test_login(tmp_path, server, anyio_backend):
    host, port = server
    file_path = tmp_path / "updates.y"
    set_config(
        host=f"http://{host}",
        port=port,
        file_path=file_path,
        room_id="room1",
    )

    with pytest.raises(RuntimeError, match="Not logged in"):
        refresh()


@pytest.mark.skipif(
    not (
        platform.system() == "Darwin" and platform.python_version().startswith("3.14.")
    ),
    reason="Only works on macos/py3.14",
)
def test_atexit(server, user, tmp_path):  # pragma: nocover
    host, port = server
    username, password = user
    repl = pexpect.spawn(
        "python -m asyncio", env=os.environ | {"PYTHON_COLORS": "0", "NO_COLOR": "1"}
    )
    repl.expect("import asyncio")
    repl.expect(">>> ")
    repl.sendline("""print("Hello, World!")""")
    repl.expect(">>> ")
    assert b"Hello, World!" in repl.before
    repl.sendline(
        """from cocat import set_config, log_in, create_catalogue, synchronize"""
    )
    repl.expect(">>> ")
    repl.sendline(
        f"""file_path = '{tmp_path / "updates.y"}'; set_config(host=f"http://{host}", port={port}, file_path=file_path, room_id="room1")"""
    )
    repl.expect(">>> ")
    repl.sendline(f"""log_in("{username}", "{password}")""")
    repl.expect(">>> ")
    repl.sendline("""await synchronize()""")
    repl.expect(">>> ")
    repl.sendline(
        """catalogue0 = create_catalogue(name="cat0", author="Paul Newton")"""
    )
    repl.expect(">>> ")
    repl.sendline("""print(catalogue0)""")
    repl.expect(">>> ")
    assert b"Paul Newton" in repl.before
    repl.sendline("""exit""")
    repl.expect("exiting asyncio REPL...")
    repl.kill(signal.SIGINT)
    repl.expect("Save changes")
    repl.sendline("""yes""")
    repl.expect("Changes have been saved.")
