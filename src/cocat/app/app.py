from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Annotated, Any

from anyio import sleep_forever
from anyio.abc import TaskStatus
from fastapi import Cookie, Depends, FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi_users import BaseUserManager, models
from pycrdt import Channel
from wiredb import Room, RoomManager, connect

from .db import create_db_and_tables
from .schemas import UserCreate, UserRead, UserUpdate
from .users import auth_backend, fastapi_users, get_user_manager, get_jwt_strategy


class StoredRoom(Room):
    def __init__(self, directory: str, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._directory = directory

    async def run(self, *args: Any, **kwargs: Any):
        await self.task_group.start(self.connect_to_file)
        await super().run(*args, **kwargs)

    async def connect_to_file(self, *, task_status: TaskStatus[None]) -> None:
        async with connect("file", doc=self.doc, path=f"{Path(self._directory) / self.id.lstrip('/')}.y"):
            task_status.started()
            await sleep_forever()


class CocatApp:
    def __init__(self, update_dir: str, db_path: str = "./test.db") -> None:

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with RoomManager(partial(StoredRoom, update_dir)) as self.room_manager:
                await create_db_and_tables(db_path)
                yield

        self.app = app = FastAPI(lifespan=lifespan)

        current_superuser = fastapi_users.current_user(active=True, superuser=True)

        app.include_router(
            fastapi_users.get_auth_router(auth_backend), prefix="/auth/jwt", tags=["auth"]
        )
        app.include_router(
            fastapi_users.get_register_router(UserRead, UserCreate),
            prefix="/auth",
            tags=["auth"],
            dependencies=[Depends(current_superuser)]
        )
        app.include_router(
            fastapi_users.get_reset_password_router(),
            prefix="/auth",
            tags=["auth"],
        )
        app.include_router(
            fastapi_users.get_verify_router(UserRead),
            prefix="/auth",
            tags=["auth"],
        )
        app.include_router(
            fastapi_users.get_users_router(UserRead, UserUpdate),
            prefix="/users",
            tags=["users"],
        )

        @app.websocket("/room/{id}")
        async def connect_room(
            id: str,
            websocket = Depends(websocket_auth),
        ):
            if websocket is None:
                return

            await websocket.accept()
            ywebsocket = YWebSocket(websocket, id)
            room = await self.room_manager.get_room(ywebsocket.path)
            await room.serve(ywebsocket)


async def websocket_auth(
    websocket: WebSocket,
    fastapiusersauth: Annotated[str | None, Cookie()] = None,
    user_manager: BaseUserManager[models.UP, models.ID] = Depends(get_user_manager),
) -> WebSocket | None:
    accept_websocket = False
    if fastapiusersauth is not None:
        user = await get_jwt_strategy().read_token(fastapiusersauth, user_manager)  # type: ignore[func-returns-value,arg-type]
        if user:
            accept_websocket = True
    if accept_websocket:
        return websocket

    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
    return None


class YWebSocket(Channel):
    def __init__(self, websocket: WebSocket, path: str) -> None:
        self._websocket = websocket
        self._path = path

    @property
    def path(self) -> str:
        return self._path

    async def __anext__(self):
        try:
            return await self._websocket.receive_bytes()
        except WebSocketDisconnect:
            raise StopAsyncIteration()

    async def send(self, message: bytes) -> None:
        await self._websocket.send_bytes(message)

    async def recv(self) -> bytes:
        return await self._websocket.receive_bytes()
