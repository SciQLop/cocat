from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Cookie, Depends, FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi_users import BaseUserManager, models
from pycrdt import Channel
from wiredb import RoomManager

from .db import create_db_and_tables
from .schemas import UserCreate, UserRead, UserUpdate
from .users import auth_backend, fastapi_users, get_user_manager, get_jwt_strategy


class CocatApp:
    def __init__(self, room_manager: RoomManager, db_path: str = "./test.db") -> None:

        @asynccontextmanager
        async def lifespan(app: FastAPI):
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
            room = await room_manager.get_room(ywebsocket.path)
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
