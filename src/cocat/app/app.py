import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Any

from anyio import CancelScope, sleep_forever
from anyio.abc import TaskStatus
from fastapi import (
    Depends,
    FastAPI,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute, APIRouter
from sqlalchemy.ext.asyncio import AsyncSession
from wire_file import AsyncFileClient
from wiredb import AsyncChannel, Room, RoomManager

from .connections import Connections
from .db import DB, User, get_db
from .db import Room as RoomModel
from .ratelimit import RateLimiter, limit, load_trusted_proxies
from .rooms import RoomError, list_members, list_user_rooms
from .routes import make_api_router, room_error_handler
from .schemas import RoomUsers, UserCreate, UserRead, UserRooms, UserUpdate
from .secret import load_secret
from .storage import remove_room_file, room_file
from .users import get_backend


def with_route_dependency(
    router: APIRouter, path: str, dependency: Callable[[Request], None]
) -> APIRouter:
    for route in router.routes:
        if isinstance(route, APIRoute) and route.path == path:
            route.dependencies.append(Depends(dependency))
            return router
    raise ValueError(f"No route {path} on the router")


class StoredRoom(Room):
    def __init__(self, directory: str, db: DB, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._directory = directory
        self._db = db

    async def run(self, *args: Any, **kwargs: Any) -> None:
        await self.task_group.start(self.connect_to_file)
        await super().run(*args, **kwargs)

    async def connect_to_file(self, *, task_status: TaskStatus[None]) -> None:
        try:
            async with AsyncFileClient(
                doc=self.doc,
                path=room_file(self._directory, self.id),
            ):
                task_status.started()
                await sleep_forever()
        finally:
            with CancelScope(shield=True):
                await self.remove_file_if_room_deleted()

    async def remove_file_if_room_deleted(self) -> None:
        async with self._db.async_session_maker() as session:
            if await session.get(RoomModel, self.id) is None:
                remove_room_file(self._directory, self.id)


class CocatApp:  # pragma: nocover
    def __init__(self, update_dir: str, db_path: str = "./test.db") -> None:
        db = get_db(db_path)
        self.db = db
        self.connections = Connections()
        backend = get_backend(db, load_secret(Path(f"{db_path}.secret")))

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with RoomManager(
                partial(StoredRoom, update_dir, db)
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

        limiter = RateLimiter(10, 60.0)
        check_limit = limit(limiter, load_trusted_proxies())

        app.include_router(
            with_route_dependency(
                backend.fastapi_users.get_auth_router(backend.auth_backend),
                "/login",
                check_limit,
            ),
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
            with_route_dependency(
                backend.fastapi_users.get_reset_password_router(),
                "/forgot-password",
                check_limit,
            ),
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
        app.add_exception_handler(RoomError, room_error_handler)
        app.include_router(
            make_api_router(db, backend, self.connections, update_dir), prefix="/api"
        )

        @app.websocket("/room/{room_id}")
        async def connect_room(
            room_id: str,
            authenticated: tuple[WebSocket, User] | None = Depends(
                backend.websocket_auth
            ),
        ):
            if authenticated is None:
                return

            websocket, user = authenticated
            await websocket.accept()
            self.connections.add(room_id, user.id, websocket)
            try:
                ywebsocket = YWebSocket(websocket, room_id)
                room = await self.room_manager.get_room(ywebsocket.id)
                await room.serve(ywebsocket)
            finally:
                self.connections.discard(room_id, user.id, websocket)

        @app.get("/rooms", response_model=UserRooms)
        async def get_rooms(
            user: User = Depends(backend.current_active_user),
            session: AsyncSession = Depends(db.get_async_session),
        ):
            return {
                "rooms": [
                    room.id for room, _ in await list_user_rooms(session, user.id)
                ]
            }

        @app.get("/room/{room_id}/users", response_model=RoomUsers)
        async def get_room_users(
            room_id: str,
            user: User = Depends(backend.current_active_user),
            session: AsyncSession = Depends(db.get_async_session),
        ):
            members = await list_members(session, room_id, user)
            return {"users": [member.email for member, _ in members]}


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
