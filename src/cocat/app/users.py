import uuid
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Cookie, Depends, Path, Request, WebSocket, status
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from .db import DB, User
from .rooms import create_personal_room, get_role


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        session = cast(SQLAlchemyUserDatabase, self.user_db).session
        await create_personal_room(session, user)
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        print(f"User {user.id} requested a password reset.")

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        print(f"User {user.id} requested a verification.")


def make_user_manager(user_db: SQLAlchemyUserDatabase, secret: str) -> UserManager:
    user_manager = UserManager(user_db)
    user_manager.reset_password_token_secret = secret
    user_manager.verification_token_secret = secret
    return user_manager


@dataclass
class Backend:
    auth_backend: Any
    current_active_user: Any
    fastapi_users: Any
    get_jwt_strategy: Any
    get_user_manager: Any
    websocket_auth: Any


def get_backend(db: DB, secret: str) -> Backend:
    async def get_user_manager(
        user_db: SQLAlchemyUserDatabase = Depends(db.get_user_db),
    ):
        yield make_user_manager(user_db, secret)

    async def websocket_auth(
        websocket: WebSocket,
        room_id: str = Path(...),
        fastapiusersauth: Annotated[str | None, Cookie()] = None,
    ) -> WebSocket | None:
        if fastapiusersauth is not None:
            async with db.async_session_maker() as session:
                user_manager = make_user_manager(
                    SQLAlchemyUserDatabase(session, User), secret
                )
                user = await get_jwt_strategy().read_token(  # type: ignore[func-returns-value]
                    fastapiusersauth, cast(Any, user_manager)
                )
                if (
                    user is not None
                    and await get_role(session, room_id, user.id) is not None
                ):
                    return websocket

        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return None

    def get_jwt_strategy() -> JWTStrategy[models.UP, models.ID]:  # pragma: nocover
        return JWTStrategy(secret=secret, lifetime_seconds=3600)

    auth_backend: AuthenticationBackend = AuthenticationBackend(
        name="cookie",
        transport=CookieTransport(),
        get_strategy=get_jwt_strategy,
    )

    fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])

    current_active_user = fastapi_users.current_user(active=True)

    return Backend(
        auth_backend=auth_backend,
        current_active_user=current_active_user,
        fastapi_users=fastapi_users,
        get_jwt_strategy=get_jwt_strategy,
        get_user_manager=get_user_manager,
        websocket_auth=websocket_auth,
    )
