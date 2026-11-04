import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Cookie, Depends, Path, Request, WebSocket, status
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, models
from fastapi_users.authentication import (
    AuthenticationBackend,
    CookieTransport,
    JWTStrategy,
)
from fastapi_users.db import SQLAlchemyUserDatabase

from .db import DB, User


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def on_after_register(
        self, user: User, request: Request | None = None
    ) -> None:
        print(f"User {user.id} has registered.")

    async def on_after_forgot_password(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        print(f"User {user.id} requested a password reset.")

    async def on_after_request_verify(
        self, user: User, token: str, request: Request | None = None
    ) -> None:
        print(f"User {user.id} requested a verification.")


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
        user_manager = UserManager(user_db)
        user_manager.reset_password_token_secret = secret
        user_manager.verification_token_secret = secret
        yield user_manager

    async def websocket_auth(
        websocket: WebSocket,
        room_id: str = Path(...),
        fastapiusersauth: Annotated[str | None, Cookie()] = None,
        user_manager: BaseUserManager[models.UP, models.ID] = Depends(get_user_manager),
    ) -> WebSocket | None:  # pragma: nocover
        accept_websocket = False
        if fastapiusersauth is not None:
            user = await get_jwt_strategy().read_token(fastapiusersauth, user_manager)  # type: ignore[func-returns-value,arg-type]
            if user and room_id in user.rooms:
                accept_websocket = True
        if accept_websocket:
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
