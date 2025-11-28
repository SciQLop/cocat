import atexit
import builtins
import time

import httpx
import keyring
import pytest
from utils import get_credential, set_password
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


def test_user_room(tmp_path, server, user, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        host, port = server
        file_path = tmp_path / "updates.y"

        set_config(
            host=f"http://{host}",
            port=port,
            file_path=file_path,
        )

        log_in(*user)


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
        username, password = user
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
