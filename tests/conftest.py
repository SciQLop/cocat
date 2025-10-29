import os
import signal
import subprocess
import time

import pytest
import requests  # type: ignore[import-untyped]


@pytest.fixture()
def server(free_tcp_port, tmp_path):
    command_list = [
        "cocat",
        "serve",
        "--host", "localhost",
        "--port", str(free_tcp_port),
        "--directory", str(tmp_path),
    ]
    p = subprocess.Popen(command_list)
    url = f"http://127.0.0.1:{free_tcp_port}"
    while True:
        try:
            requests.get(url)
        except requests.exceptions.ConnectionError:
            time.sleep(0.1)
        else:
            break
    yield url
    os.kill(p.pid, signal.SIGINT)
    p.wait()
