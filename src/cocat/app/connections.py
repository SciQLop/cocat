from contextlib import suppress
from uuid import UUID

from fastapi import WebSocket, status


class Connections:
    def __init__(self) -> None:
        self._rooms: dict[str, dict[UUID, set[WebSocket]]] = {}

    def add(self, room_id: str, user_id: UUID, websocket: WebSocket) -> None:
        self._rooms.setdefault(room_id, {}).setdefault(user_id, set()).add(websocket)

    def discard(self, room_id: str, user_id: UUID, websocket: WebSocket) -> None:
        users = self._rooms.get(room_id)
        if users is None:
            return
        sockets = users.get(user_id)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            del users[user_id]
        if not users:
            del self._rooms[room_id]

    async def close(self, room_id: str, user_id: UUID | None = None) -> None:
        users = self._rooms.get(room_id, {})
        groups = (
            list(users.values()) if user_id is None else [users.get(user_id, set())]
        )
        for sockets in groups:
            for websocket in list(sockets):
                with suppress(OSError, RuntimeError):
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
