import os
import signal
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import uuid4

import anyio
import pytest
from fastapi.testclient import TestClient
from utils import add_user_to_room, create_user, wait_for_server

from cocat.app.app import CocatApp
from cocat.cli import _create_user


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
    add_user_to_room(email, room_id, db_path)
    yield email, password


@pytest.fixture()
def server(free_tcp_port: int, update_dir: str, db_path: str):
    host = "127.0.0.1"
    command = [
        "cocat",
        "serve",
        "--host",
        host,
        "--port",
        str(free_tcp_port),
        "--update_dir",
        update_dir,
        "--db_path",
        db_path,
    ]
    p = subprocess.Popen(command)
    url = f"http://{host}:{free_tcp_port}"
    wait_for_server(url, p)
    yield host, free_tcp_port
    os.kill(p.pid, signal.SIGINT)
    p.wait()
