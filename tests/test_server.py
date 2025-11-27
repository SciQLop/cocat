from uuid import uuid4

import httpx
import pytest
from anyio import fail_after, sleep
from utils import add_user_to_room, create_user
from wire_file import AsyncFileClient
from wire_websocket import AsyncWebSocketClient, AsyncWebSocketServer

from cocat import DB

pytestmark = pytest.mark.anyio


async def test_websocket(free_tcp_port, tmp_path):
    update_path = tmp_path / "updates.y"
    async with AsyncWebSocketServer(host="localhost", port=free_tcp_port):
        async with (
            AsyncWebSocketClient(
                host="http://localhost", port=free_tcp_port
            ) as client0,
            AsyncWebSocketClient(
                host="http://localhost", port=free_tcp_port
            ) as client1,
            AsyncFileClient(doc=client0.doc, path=update_path),
        ):
            db0 = DB(doc=client0.doc)
            db1 = DB(doc=client1.doc)

            async with db0.transaction():
                event0 = db0.create_event(
                    start="2025-01-31",
                    stop="2026-01-31",
                    author="Paul",
                )
                catalogue0 = db0.create_catalogue(
                    name="cat",
                    author="John",
                )
                catalogue0.add_events(event0)

            with fail_after(1):
                while True:
                    await sleep(0.01)
                    if db1.events and db1.catalogues:
                        assert db1.events == {event0}
                        assert db1.catalogues == {catalogue0}
                        break

            async with db1.transaction():
                event1 = db1.create_event(
                    start="2027-01-31",
                    stop="2028-01-31",
                    author="Mike",
                )
                catalogue1 = db1.get_catalogue(str(catalogue0.uuid))
                catalogue1.add_events(event1)

            with pytest.raises(
                RuntimeError, match="No catalogue found with name or UUID"
            ):
                db1.get_catalogue(uuid4())

            with fail_after(1):
                while True:
                    await sleep(0.01)
                    if len(db0.events) > 1:
                        assert db0.events == {event0, event1}
                        assert db0.catalogues == {catalogue1}
                        break

            await sleep(0.1)

    db2 = DB()
    async with AsyncFileClient(doc=db2.doc, path=update_path):
        pass
    assert db2.events == {event0, event1}
    assert db2.catalogues == {catalogue1}


async def test_origin(server, user, room_id):
    host, port = server
    username, password = user
    data = {"username": username, "password": password}
    response = httpx.post(f"http://{host}:{port}/auth/jwt/login", data=data)
    cookie = response.cookies.get("fastapiusersauth")
    cookies = httpx.Cookies()
    cookies.set("fastapiusersauth", cookie)
    async with (
        AsyncWebSocketClient(
            id=f"room/{room_id}",
            host=f"http://{host}",
            port=port,
            cookies=cookies,
        ) as client0,
        AsyncWebSocketClient(
            id=f"room/{room_id}",
            host=f"http://{host}",
            port=port,
            cookies=cookies,
        ) as client1,
    ):
        db0 = DB(doc=client0.doc)
        db1 = DB(doc=client1.doc)
        events0 = []
        events1 = []

        def callback0(event):
            events0.append(event)  # pragma: nocover

        def callback1(event):
            events1.append(event)

        db0.on_create_event(callback0)
        db1.on_create_event(callback1)
        event0 = db0.create_event(
            start="2025-01-31",
            stop="2026-01-31",
            author="Paul",
        )

        with fail_after(1):
            while True:
                await sleep(0.01)
                if events1:
                    assert not events0
                    assert events1 == [event0]
                    break


async def test_api(server, user, room_id, db_path):
    host, port = server
    username, password = user
    data = {"username": username, "password": password}
    response = httpx.post(f"http://{host}:{port}/auth/jwt/login", data=data)
    cookie = response.cookies.get("fastapiusersauth")
    cookies = httpx.Cookies()
    cookies.set("fastapiusersauth", cookie)

    response = httpx.get(f"http://{host}:{port}/rooms")
    assert response.json() == {"detail": "Unauthorized"}

    response = httpx.get(f"http://{host}:{port}/rooms", cookies=cookies)
    user_room_id = username[: username.find("@")]
    assert set(response.json()["rooms"]) == set([room_id, user_room_id])

    email0 = "user0@example.com"
    create_user(email=email0, password="pwd", db_path=db_path)
    add_user_to_room(email=email0, room_id=room_id, db_path=db_path)

    response = httpx.get(f"http://{host}:{port}/room/{room_id}/users", cookies=cookies)
    assert response.json() == {"users": [username, email0]}
