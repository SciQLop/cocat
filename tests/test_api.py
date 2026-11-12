import atexit
import builtins
import time
from contextlib import suppress
from types import SimpleNamespace

import httpx
import keyring
import pytest
from conftest import running_server
from utils import get_credential, set_password
from wire_file import FileClient
from wire_websocket import WebSocketClient

import cocat.api
from cocat import (
    DB,
    api,
    create_catalogue,
    create_event,
    get_catalogue,
    get_event,
    log_in,
    log_out,
    refresh,
    save,
    set_config,
)
from cocat.app.storage import room_file
from cocat.cli import get_user


def test_user_room(tmp_path, server, user, room_id, db_path, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        host, port = server
        file_path = tmp_path / "updates.y"

        cocat.api.SESSION.room_id = None
        set_config(
            host=f"http://{host}",
            port=port,
            file_path=file_path,
        )

        log_in(*user)

        _, rooms = get_user(email=user[0], db_path=db_path)
        assert cocat.api.SESSION.room_id in rooms
        assert cocat.api.SESSION.room_id != room_id
        assert len(cocat.api.SESSION.room_id) == 32


def test_api(tmp_path, server, user, room_id, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        host, port = server
        username, password = user
        data = {"username": username, "password": password}
        response = httpx.post(f"http://{host}:{port}/auth/jwt/login", data=data)
        cookie = response.cookies.get("fastapiusersauth")
        cookies = httpx.Cookies()
        cookies.set("fastapiusersauth", cookie)
        with WebSocketClient(
            id=f"room/{room_id}",
            auto_push=True,
            host=f"http://{host}",
            port=port,
            cookies=cookies,
        ) as client:
            db = DB(doc=client.doc)

            file_path = tmp_path / "updates.y"
            set_config(
                host=f"http://{host}",
                port=port,
                file_path=file_path,
                room_id=room_id,
            )
            log_in(*user)

            catalogue0 = create_catalogue(name="cat0", author="Paul")
            event0 = create_event(
                start="2025-01-30",
                stop="2026-01-30",
                author="Mike",
            )
            assert event0 == get_event(event0.uuid)
            assert catalogue0 == get_catalogue(catalogue0.uuid)

            save()

            for _ in range(10):
                try:
                    catalogue1 = db.get_catalogue("cat0")
                    assert catalogue0 == catalogue1
                    break
                except Exception as exc:
                    if not str(exc).startswith("No catalogue found"):
                        raise  # pragma: nocover
                time.sleep(0.1)
                client.pull()
            else:  # pragma: nocover
                raise TimeoutError()

            event1 = db.create_event(
                start="2025-01-31",
                stop="2026-01-31",
                author="John",
            )

            for _ in range(10):
                try:
                    event0 = get_event(event1.uuid)
                    assert event0 == event1
                    break
                except Exception as exc:
                    if not str(exc).startswith("No event found"):
                        raise  # pragma: nocover
                time.sleep(0.1)
                refresh()
            else:  # pragma: nocover
                raise TimeoutError()

        log_out()

        with pytest.raises(RuntimeError, match="Wrong username or password"):
            log_in("foo", "bar")


def test_login(tmp_path, server, user, room_id, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        host, port = server
        username, _password = user
        file_path = tmp_path / "updates.y"
        set_config(
            host=f"http://{host}",
            port=port,
            file_path=file_path,
            room_id=room_id,
        )

        with pytest.raises(RuntimeError, match="Not logged in"):
            refresh()

        with pytest.raises(RuntimeError, match="Username or password not provided"):
            log_in(username, connect=False)

        log_in(*user, connect=False)
        log_in(connect=False)


def test_login_with_port_in_host(tmp_path, server, room_id, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        host, port = server
        file_path = tmp_path / "updates.y"
        set_config(
            host=f"http://{host}:{port}",
            file_path=file_path,
            room_id=room_id,
        )

        with pytest.raises(RuntimeError, match="Not logged in"):
            refresh()

        assert api.SESSION.host == f"http://{host}"
        assert api.SESSION.port == port


def test_atexit(room_id, server, user, tmp_path, monkeypatch, capsys):
    with monkeypatch.context() as m:
        m.setattr(builtins, "input", lambda _: "yes")
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        host, port = server
        username, password = user
        file_path = tmp_path / "updates.y"
        set_config(
            host=f"http://{host}", port=port, file_path=file_path, room_id=room_id
        )
        log_in(username, password)
        create_catalogue(name="cat0", author="Paul Newton")
        cocat.api.save_on_exit()
        captured = capsys.readouterr()
        assert captured.out == "Changes have been saved.\n"
        atexit.unregister(cocat.api.save_on_exit)


def test_default_room(monkeypatch):
    def failed(*args, **kwargs):
        return httpx.Response(500)

    monkeypatch.setattr(cocat.api.httpx, "get", failed)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        cocat.api._default_room("http://localhost:8000/")

    def empty(*args, **kwargs):
        return httpx.Response(200, json=[])

    monkeypatch.setattr(cocat.api.httpx, "get", empty)
    with pytest.raises(RuntimeError, match="No room available"):
        cocat.api._default_room("http://localhost:8000/")

    def rooms(*args, **kwargs):
        return httpx.Response(
            200, json=[{"id": "room1", "name": "Lab", "role": "editor"}]
        )

    monkeypatch.setattr(cocat.api.httpx, "get", rooms)
    assert cocat.api._default_room("http://localhost:8000/") == "room1"


def test_save_keeps_a_local_copy(tmp_path, server, user, room_id, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        host, port = server
        file_path = tmp_path / "updates.y"
        set_config(
            host=f"http://{host}", port=port, file_path=file_path, room_id=room_id
        )
        log_in(*user)
        event = create_event(start="2025-01-31", stop="2026-01-31", author="Paul")
        save()
        log_out()

        local = DB()
        with FileClient(doc=local.doc, path=file_path) as file:
            file.pull()
        assert event.uuid in {e.uuid for e in local.events}


def test_edits_saved_during_an_outage_reach_the_server_later(
    tmp_path, free_tcp_port, user, room_id, update_dir, db_path, monkeypatch
):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        port = free_tcp_port
        file_path = tmp_path / "updates.y"
        with running_server(port, update_dir, db_path) as host:
            set_config(
                host=f"http://{host}", port=port, file_path=file_path, room_id=room_id
            )
            log_in(*user)

        event = create_event(start="2025-01-31", stop="2026-01-31", author="Paul")
        # Windows buffers a send to a closed socket, so save() may not notice the
        # outage; the edit must reach the server either way.
        with suppress(RuntimeError):
            save()

        m.setattr(cocat.api.SESSION, "db", DB())  # a new process: only the file is left
        with running_server(port, update_dir, db_path):
            log_in(*user)
            save()
            log_out()

        stored = DB()
        with FileClient(doc=stored.doc, path=room_file(update_dir, room_id)) as file:
            file.pull()
        assert event.uuid in {e.uuid for e in stored.events}


def test_save_writes_the_file_even_when_the_server_is_unreachable(monkeypatch):
    written = []

    def unreachable():
        raise OSError("connection reset")

    monkeypatch.setattr(api.SESSION, "connected", True)
    monkeypatch.setattr(
        api.SESSION, "file", SimpleNamespace(push=lambda: written.append(True)), False
    )
    monkeypatch.setattr(api.SESSION, "client", SimpleNamespace(push=unreachable), False)

    with pytest.raises(RuntimeError, match="saved locally"):
        save()
    assert written == [True]
