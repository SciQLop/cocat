from uuid import uuid4

import httpx
import pytest
from anyio import sleep
from wire_websocket import AsyncWebSocketClient

from cocat import DB

pytestmark = pytest.mark.anyio


async def test_room_catalogues(server, user, room_id):
    host, port = server
    username, password = user
    data = {"username": username, "password": password}
    response = httpx.post(f"http://{host}:{port}/auth/jwt/login", data=data)
    cookie = response.cookies.get("fastapiusersauth")
    cookies = httpx.Cookies()
    cookies.set("fastapiusersauth", cookie)

    # unauthenticated
    response = httpx.get(f"http://{host}:{port}/rooms/{room_id}/catalogues")
    assert response.status_code == 401

    # room not accessible by user
    response = httpx.get(
        f"http://{host}:{port}/rooms/{uuid4()}/catalogues", cookies=cookies
    )
    assert response.status_code == 403

    # empty room
    response = httpx.get(
        f"http://{host}:{port}/rooms/{room_id}/catalogues", cookies=cookies
    )
    assert response.status_code == 200
    assert response.json() == {"catalogues": []}

    # create catalogue with two events via WebSocket
    async with AsyncWebSocketClient(
        id=f"room/{room_id}",
        host=f"http://{host}",
        port=port,
        cookies=cookies,
    ) as client:
        db = DB(doc=client.doc)
        cat = db.create_catalogue(name="Solar Wind Events", author="tester")
        cat_uuid = str(cat._uuid)
        e1 = db.create_event(start="2024-03-15", stop="2024-03-16", author="tester")
        e2 = db.create_event(start="2024-01-10", stop="2024-01-11", author="tester")
        cat.add_events(e1)
        cat.add_events(e2)
        await sleep(0.2)

    response = httpx.get(
        f"http://{host}:{port}/rooms/{room_id}/catalogues", cookies=cookies
    )
    assert response.status_code == 200
    catalogues = response.json()["catalogues"]
    assert len(catalogues) == 1
    assert catalogues[0]["uuid"] == cat_uuid
    assert catalogues[0]["name"] == "Solar Wind Events"
    assert catalogues[0]["nb_events"] == 2


async def test_catalogue_and_events(server, user, room_id):
    host, port = server
    username, password = user
    data = {"username": username, "password": password}
    response = httpx.post(f"http://{host}:{port}/auth/jwt/login", data=data)
    cookie = response.cookies.get("fastapiusersauth")
    cookies = httpx.Cookies()
    cookies.set("fastapiusersauth", cookie)

    # not found
    fake_uuid = str(uuid4())
    assert (
        httpx.get(
            f"http://{host}:{port}/catalogues/{fake_uuid}", cookies=cookies
        ).status_code
        == 404
    )
    assert (
        httpx.get(
            f"http://{host}:{port}/catalogues/{fake_uuid}/events", cookies=cookies
        ).status_code
        == 404
    )

    # create data
    async with AsyncWebSocketClient(
        id=f"room/{room_id}",
        host=f"http://{host}",
        port=port,
        cookies=cookies,
    ) as client:
        db = DB(doc=client.doc)
        cat = db.create_catalogue(name="Solar Wind Events", author="tester")
        cat_uuid = str(cat._uuid)
        e1 = db.create_event(start="2024-03-15", stop="2024-03-16", author="tester")
        e2 = db.create_event(start="2024-01-10", stop="2024-01-11", author="tester")
        cat.add_events(e1)
        cat.add_events(e2)
        await sleep(0.2)

    # GET /catalogues/{uuid}
    response = httpx.get(f"http://{host}:{port}/catalogues/{cat_uuid}", cookies=cookies)
    assert response.status_code == 200
    data = response.json()
    assert data["uuid"] == cat_uuid
    assert data["name"] == "Solar Wind Events"
    assert data["room_id"] == room_id
    assert data["nb_events"] == 2

    # GET /catalogues/{uuid}/events — sorted by start
    response = httpx.get(
        f"http://{host}:{port}/catalogues/{cat_uuid}/events", cookies=cookies
    )
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 2
    assert events[0]["start"] == "2024-01-10T00:00:00"
    assert events[1]["start"] == "2024-03-15T00:00:00"
