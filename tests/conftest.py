import os
import signal
import subprocess
from uuid import uuid4

import pytest
from utils import add_user_to_room, create_user, wait_for_server


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
