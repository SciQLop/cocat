from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Any
import os

from anyio import sleep_forever
from anyio.abc import TaskStatus
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from wire_file import AsyncFileClient
from wiredb import AsyncChannel, Room, RoomManager

from .db import get_db
from .schemas import UserCreate, UserRead, UserUpdate
from .users import get_backend


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

        root_path = os.environ.get('COCAT_PROXY_PREFIX', '')
        if root_path:
            if not root_path.startswith('/'):
                root_path = '/' + root_path
            if root_path.endswith('/'):
                root_path = root_path[:-1]
        else:
            root_path = ''

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
            websocket=Depends(backend.websocket_auth),
        ):
            if websocket is None:
                return

            await websocket.accept()
            ywebsocket = YWebSocket(websocket, room_id)
            room = await self.room_manager.get_room(ywebsocket.id)
            await room.serve(ywebsocket)


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
