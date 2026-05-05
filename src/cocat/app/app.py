import os
from contextlib import asynccontextmanager
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from anyio import sleep_forever
from anyio.abc import TaskStatus
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from wire_file import AsyncFileClient
from wiredb import AsyncChannel, Room, RoomManager

from .db import User, get_db
from ..db import DB as CrdtDB
from .schemas import RoomUsers, UserCreate, UserRead, UserRooms, UserUpdate
from .users import get_backend


def _dt_to_iso(dt: Any) -> str:
    """Return ISO 8601 timestamp without timezone suffix."""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    return str(dt).replace("Z", "").split("+")[0]


class StoredRoom(Room):  # pragma: nocover
    def __init__(self, directory: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._directory = directory

    async def run(self, *args: Any, **kwargs: Any):
        await self.task_group.start(self.connect_to_file)
        await super().run(*args, **kwargs)

    async def connect_to_file(self, *, task_status: TaskStatus[None]) -> None:
        async with AsyncFileClient(
            doc=self.doc,
            path=f"{Path(self._directory) / self.id.lstrip('/')}.y",
        ):
            task_status.started()
            await sleep_forever()


class CocatApp:  # pragma: nocover
    def __init__(self, update_dir: str, db_path: str = "./test.db") -> None:
        db = get_db(db_path)
        backend = get_backend(db)

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with RoomManager(
                partial(StoredRoom, update_dir)
            ) as self.room_manager:
                await db.create_db_and_tables()
                yield

        root_path = os.environ.get("COCAT_PROXY_PREFIX", "")
        if root_path:
            root_path = "/" + root_path.strip("/")

        self.app = app = FastAPI(lifespan=lifespan, root_path=root_path)

        app.add_middleware(
            CORSMiddleware,
            allow_origins=[],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        current_superuser = backend.fastapi_users.current_user(
            active=True, superuser=True
        )

        app.include_router(
            backend.fastapi_users.get_auth_router(backend.auth_backend),
            prefix="/auth/jwt",
            tags=["auth"],
        )
        app.include_router(
            backend.fastapi_users.get_register_router(UserRead, UserCreate),
            prefix="/auth",
            tags=["auth"],
            dependencies=[Depends(current_superuser)],
        )
        app.include_router(
            backend.fastapi_users.get_reset_password_router(),
            prefix="/auth",
            tags=["auth"],
        )
        app.include_router(
            backend.fastapi_users.get_verify_router(UserRead),
            prefix="/auth",
            tags=["auth"],
        )
        app.include_router(
            backend.fastapi_users.get_users_router(UserRead, UserUpdate),
            prefix="/users",
            tags=["users"],
        )

        @app.websocket("/room/{room_id}")
        async def connect_room(
            room_id: str,
            websocket: WebSocket | None = Depends(backend.websocket_auth),
        ):
            if websocket is None:
                return

            await websocket.accept()
            ywebsocket = YWebSocket(websocket, room_id)
            room = await self.room_manager.get_room(ywebsocket.id)
            await room.serve(ywebsocket)

        @app.get("/rooms", response_model=UserRooms)
        async def get_rooms(
            user: User = Depends(backend.current_active_user),
        ):
            return user

        @app.get("/room/{room_id}/users", response_model=RoomUsers)
        async def get_room_users(room_id: str):
            async with db.async_session_maker() as session:
                statement = select(User)
                users = (await session.execute(statement)).unique().all()
            return {
                "users": [usr.User.email for usr in users if room_id in usr.User.rooms]
            }

        @app.get("/rooms/{room_id}/catalogues")
        async def get_room_catalogues(
            room_id: str,
            user: User = Depends(backend.current_active_user),
        ):
            if room_id not in user.rooms:
                raise HTTPException(status_code=403, detail="Not authorized")
            room = await self.room_manager.get_room(room_id)
            crdt_db = CrdtDB(doc=room.doc)
            return {
                "catalogues": [
                    {
                        "uuid": str(cat._uuid),
                        "name": cat.name,
                        "nb_events": len(cat.events),
                        "author": cat._map.get("author", ""),
                        "tags": list(cat._map.get("tags", {}).keys() if hasattr(cat._map.get("tags", None), "keys") else []),
                        "attributes": dict(cat._map.get("attributes", {}) or {}),
                    }
                    for cat in crdt_db.catalogues
                ]
            }

        @app.get("/catalogues/{uuid}")
        async def get_catalogue(
            uuid: str,
            user: User = Depends(backend.current_active_user),
        ):
            for room_id in user.rooms:
                room = await self.room_manager.get_room(room_id)
                crdt_db = CrdtDB(doc=room.doc)
                for cat in crdt_db.catalogues:
                    if str(cat._uuid) == uuid:
                        return {
                            "uuid": uuid,
                            "room_id": room_id,
                            "name": cat.name,
                            "nb_events": len(cat.events),
                            "author": cat._map.get("author", ""),
                            "tags": list(cat._map.get("tags", {}).keys() if hasattr(cat._map.get("tags", None), "keys") else []),
                            "attributes": dict(cat._map.get("attributes", {}) or {}),
                        }
            raise HTTPException(status_code=404, detail="Catalogue not found")

        @app.get("/catalogues/{uuid}/events")
        async def get_catalogue_events(
            uuid: str,
            user: User = Depends(backend.current_active_user),
        ):
            for room_id in user.rooms:
                room = await self.room_manager.get_room(room_id)
                crdt_db = CrdtDB(doc=room.doc)
                for cat in crdt_db.catalogues:
                    if str(cat._uuid) == uuid:
                        events = sorted(cat.events, key=lambda e: e.start)
                        return {
                            "uuid": uuid,
                            "name": cat.name,
                            "room_id": room_id,
                            "author": cat._map.get("author", ""),
                            "tags": list(cat._map.get("tags", {}).keys() if hasattr(cat._map.get("tags", None), "keys") else []),
                            "events": [
                                {
                                    "uuid": str(e._uuid),
                                    "start": _dt_to_iso(e.start),
                                    "stop": _dt_to_iso(e.stop),
                                    "author": e._map.get("author", ""),
                                    "tags": list(e._map.get("tags", {}).keys() if hasattr(e._map.get("tags", None), "keys") else []),
                                    "attributes": dict(e._map.get("attributes", {}) or {}),
                                }
                                for e in events
                            ],
                        }
            raise HTTPException(status_code=404, detail="Catalogue not found")


class YWebSocket(AsyncChannel):  # pragma: nocover
    def __init__(self, websocket: WebSocket, path: str) -> None:
        self._websocket = websocket
        self._path = path

    @property
    def id(self) -> str:
        return self._path

    async def __anext__(self):
        try:
            return await self._websocket.receive_bytes()
        except WebSocketDisconnect:
            raise StopAsyncIteration()

    async def send(self, message: bytes) -> None:
        await self._websocket.send_bytes(message)

    async def receive(self) -> bytes:
        return await self._websocket.receive_bytes()
