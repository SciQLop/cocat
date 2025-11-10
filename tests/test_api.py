import atexit
import builtins
import time

import httpx
import pytest
from httpx_ws import WebSocketUpgradeError
from wire_websocket import WebSocketClient

import cocat.api
from cocat import (
    DB,
    connect,
    create_catalogue,
    create_event,
    get_catalogue,
    get_event,
    log_in,
    log_out,
    refresh,
    save,
    set_config,
    synchronize,
)


def test_api(tmp_path, server, user, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        host, port = server
        username, password = user
        data = {"username": username, "password": password}
        response = httpx.post(f"http://{host}:{port}/auth/jwt/login", data=data)
        cookie = response.cookies.get("fastapiusersauth")
        cookies = httpx.Cookies()
        cookies.set("fastapiusersauth", cookie)
        with WebSocketClient(
            id="room/room1",
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
                room_id="room1",
            )
            log_in(*user)
            synchronize()

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

        with pytest.raises(WebSocketUpgradeError):
            connect()


def test_login(tmp_path, server, monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        host, port = server
        file_path = tmp_path / "updates.y"
        set_config(
            host=f"http://{host}",
            port=port,
            file_path=file_path,
            room_id="room1",
        )

        with pytest.raises(RuntimeError, match="Not logged in"):
            refresh()


def test_atexit(server, user, tmp_path, monkeypatch, capsys):
    with monkeypatch.context() as m:
        m.setattr(builtins, "input", lambda _: "yes")
        host, port = server
        username, password = user
        file_path = tmp_path / "updates.y"
        set_config(
            host=f"http://{host}", port=port, file_path=file_path, room_id="room1"
        )
        log_in(username, password)
        synchronize()
        create_catalogue(name="cat0", author="Paul Newton")
        cocat.api.save_on_exit()
        captured = capsys.readouterr()
        assert captured.out == "Changes have been saved.\n"
        atexit.unregister(cocat.api.save_on_exit)
