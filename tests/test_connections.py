from typing import cast
from uuid import UUID, uuid4

import anyio
import anyio.lowlevel
import pytest
from fastapi import WebSocket

from cocat.app.connections import Connections

pytestmark = pytest.mark.anyio


class FakeWebSocket:
    def __init__(self) -> None:
        self.closed: list[int] = []

    async def close(self, code: int = 1000) -> None:
        self.closed.append(code)


class BrokenWebSocket:
    async def close(self, code: int = 1000) -> None:
        raise RuntimeError("already closed")


class SelfDiscardingWebSocket:
    """A socket whose close suspends and unregisters itself, like the real route."""

    def __init__(self, connections: Connections, room_id: str, user_id: UUID) -> None:
        self._connections = connections
        self._room_id = room_id
        self._user_id = user_id
        self.closed: list[int] = []

    async def close(self, code: int = 1000) -> None:
        await anyio.lowlevel.checkpoint()
        self.closed.append(code)
        self._connections.discard(self._room_id, self._user_id, cast(WebSocket, self))


def fake() -> tuple[WebSocket, list[int]]:
    socket = FakeWebSocket()
    return cast(WebSocket, socket), socket.closed


async def test_add_and_discard_removes_the_socket():
    connections = Connections()
    room_id, user_id = "lab", uuid4()
    websocket, closed = fake()

    connections.add(room_id, user_id, websocket)
    connections.discard(room_id, user_id, websocket)

    await connections.close(room_id)
    assert closed == []


async def test_discard_ignores_unknown_rooms_and_users():
    connections = Connections()
    room_id, user_id = "lab", uuid4()
    websocket, closed = fake()
    connections.add(room_id, user_id, websocket)

    connections.discard("other", user_id, websocket)
    connections.discard(room_id, uuid4(), websocket)

    await connections.close(room_id)
    assert closed == [1008]


async def test_close_targets_one_user():
    connections = Connections()
    room_id = "lab"
    alice, bob = uuid4(), uuid4()
    alice_socket, alice_closed = fake()
    bob_socket, bob_closed = fake()
    connections.add(room_id, alice, alice_socket)
    connections.add(room_id, bob, bob_socket)

    await connections.close(room_id, alice)

    assert alice_closed == [1008]
    assert bob_closed == []


async def test_close_targets_a_whole_room():
    connections = Connections()
    room_id = "lab"
    alice, bob = uuid4(), uuid4()
    alice_socket, alice_closed = fake()
    bob_socket, bob_closed = fake()
    connections.add(room_id, alice, alice_socket)
    connections.add(room_id, bob, bob_socket)

    await connections.close(room_id)

    assert alice_closed == [1008]
    assert bob_closed == [1008]


async def test_close_survives_sockets_that_discard_themselves():
    connections = Connections()
    room_id = "lab"
    alice, bob = uuid4(), uuid4()
    alice_socket = SelfDiscardingWebSocket(connections, room_id, alice)
    bob_socket = SelfDiscardingWebSocket(connections, room_id, bob)
    connections.add(room_id, alice, cast(WebSocket, alice_socket))
    connections.add(room_id, bob, cast(WebSocket, bob_socket))

    await connections.close(room_id)

    assert alice_socket.closed == [1008]
    assert bob_socket.closed == [1008]


async def test_close_tolerates_already_closed_sockets():
    connections = Connections()
    connections.add("lab", uuid4(), cast(WebSocket, BrokenWebSocket()))

    await connections.close("lab")
