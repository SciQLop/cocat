import os
import signal
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

import anyio
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect
from utils import create_room, create_user, wait_for_server

from cocat.app.app import CocatApp
from cocat.app.db import User, get_db
from cocat.cli import _create_user


async def make_orm_user(session: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.commit()
    return user


def assert_websocket_refused(
    client: TestClient, url: str, headers: dict[str, str] | None = None
) -> None:
    with pytest.raises(WebSocketDisconnect) as refused:
        client.websocket_connect(url, headers=headers).__enter__()
    assert refused.value.code == 1008


@pytest.fixture()
async def session(tmp_path):
    db = get_db(str(tmp_path / "u.db"))
    await db.create_db_and_tables()
    async with db.async_session_maker() as session:
        yield session


@dataclass
class AppClient:
    client: TestClient
    db_path: str
    update_dir: str


@pytest.fixture()
def app_client(update_dir: str, db_path: str) -> Iterator[AppClient]:
    with TestClient(
        CocatApp(update_dir, db_path).app, base_url="https://testserver"
    ) as client:
        yield AppClient(client=client, db_path=db_path, update_dir=update_dir)


def make_user(db_path: str, email: str, password: str = "pwd") -> None:
    anyio.run(_create_user, email, password, False, db_path)


def login(client: TestClient, email: str, password: str = "pwd") -> None:
    response = client.post(
        "/auth/jwt/login", data={"username": email, "password": password}
    )
    assert response.status_code == 204


def ws_headers(client: TestClient) -> dict[str, str]:
    """Headers to send a login cookie over a websocket.

    `TestClient.websocket_connect` always uses `ws://`, so httpx would not send the
    `Secure` cookie by itself.
    """
    return {"cookie": f"fastapiusersauth={client.cookies['fastapiusersauth']}"}


@pytest.fixture()
def update_dir(tmp_path):
    update_dir = tmp_path / "update_dir"
    update_dir.mkdir()
    yield str(update_dir)


@pytest.fixture()
def db_path(tmp_path):
    yield str(tmp_path / "test.db")


@pytest.fixture()
def room_id():
    return str(uuid4())


@pytest.fixture()
def user(db_path: str, room_id: str):
    email = f"user_{uuid4().hex}@foo.com"
    password = f"pwd_{uuid4().hex}"
    create_user(email, password, db_path)
    create_room(email, room_id, db_path)
    yield email, password


@contextmanager
def running_server(port: int, update_dir: str, db_path: str) -> Iterator[str]:
    host = "127.0.0.1"
    command = [
        "cocat",
        "serve",
        "--host",
        host,
        "--port",
        str(port),
        "--update_dir",
        update_dir,
        "--db_path",
        db_path,
    ]
    p = subprocess.Popen(command)
    try:
        wait_for_server(f"http://{host}:{port}", p)
        yield host
    finally:
        os.kill(p.pid, signal.SIGINT)
        p.wait()


@pytest.fixture()
def server(free_tcp_port: int, update_dir: str, db_path: str):
    with running_server(free_tcp_port, update_dir, db_path) as host:
        yield host, free_tcp_port
