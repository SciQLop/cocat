import os
import signal
import subprocess
import time
from uuid import uuid4

import pytest
import requests  # type: ignore[import-untyped]


@pytest.fixture()
def update_dir(tmp_path):
    update_dir = tmp_path / "update_dir"
    update_dir.mkdir()
    yield str(update_dir)


@pytest.fixture()
def db_path(tmp_path):
    yield str(tmp_path / "test.db")


@pytest.fixture()
def user(db_path: str):
    email = f"user_{uuid4().hex}@foo.com"
    password = f"pwd_{uuid4().hex}"
    command = [
        "cocat",
        "create-user",
        "--email", email,
        "--password", password,
        "--db_path", db_path,
    ]
    subprocess.check_call(command)
    yield email, password

@pytest.fixture()
def server(free_tcp_port: int, update_dir: str, db_path: str):
    host = "127.0.0.1"
    command = [
        "cocat",
        "serve",
        "--host", host,
        "--port", str(free_tcp_port),
        "--update_dir", update_dir,
        "--db_path", db_path,
    ]
    p = subprocess.Popen(command)
    url = f"http://{host}:{free_tcp_port}"
    while True:
        try:
            requests.get(url)
        except requests.exceptions.ConnectionError:
            time.sleep(0.1)
        else:
            break
    yield host, free_tcp_port
    os.kill(p.pid, signal.SIGINT)
    p.wait()
