import re

import keyring
import pytest
from fastapi_users.exceptions import UserAlreadyExists
from httpx_ws import WebSocketUpgradeError
from utils import get_credential, set_password

import cocat
from cocat import log_in, set_config
from cocat.cli import (
    add_user_to_room,
    create_room,
    create_user,
    get_user,
    remove_user_from_room,
    set_room_owner,
)


def test_user(tmp_path, server, room_id, monkeypatch, capsys):
    host, port = server
    db_path = str(tmp_path / "test.db")
    file_path = tmp_path / "updates.y"
    email = "a@b.com"
    password = "pwd"
    other_email = "owner@b.com"
    missing_room_id = "missing"
    room_id0 = room_id

    user = create_user(email=email, password=password, db_path=db_path)

    with pytest.raises(UserAlreadyExists):
        user = create_user(email=email, password=password, db_path=db_path)

    assert user.email == email
    user, rooms = get_user(email=email, db_path=db_path)
    assert len(rooms) == 1
    personal_room_id = rooms[0]
    assert re.fullmatch(r"[0-9a-f]{32}", personal_room_id)
    assert "a" not in rooms

    create_user(email=other_email, password=password, db_path=db_path)
    create_room(owner=other_email, room_id=room_id0, db_path=db_path)
    user, owner_rooms = get_user(email=other_email, db_path=db_path)
    assert room_id0 in owner_rooms
    add_user_to_room(email=email, room_id=room_id0, db_path=db_path)

    user, rooms = get_user(email=email, db_path=db_path)
    assert set(rooms) == {personal_room_id, room_id0}

    with pytest.raises(SystemExit) as excinfo:
        add_user_to_room(email=email, room_id=missing_room_id, db_path=db_path)
    assert excinfo.value.code == 1
    assert "does not exist" in capsys.readouterr().out

    with pytest.raises(SystemExit) as excinfo:
        remove_user_from_room(email=other_email, room_id=room_id0, db_path=db_path)
    assert excinfo.value.code == 1
    assert "owner cannot leave" in capsys.readouterr().out

    with pytest.raises(SystemExit) as excinfo:
        set_room_owner(email=email, room_id=missing_room_id, db_path=db_path)
    assert excinfo.value.code == 1
    assert "not a member of room missing" in capsys.readouterr().out

    with pytest.raises(SystemExit) as excinfo:
        create_room(owner=other_email, room_id=room_id0, db_path=db_path)
    assert excinfo.value.code == 1
    assert "already exists" in capsys.readouterr().out

    set_room_owner(email=email, room_id=room_id0, db_path=db_path)

    user, rooms = get_user(email=other_email, db_path=db_path)
    assert room_id0 in rooms

    with pytest.raises(SystemExit) as excinfo:
        remove_user_from_room(email=email, room_id=room_id0, db_path=db_path)
    assert excinfo.value.code == 1
    assert "owner cannot leave" in capsys.readouterr().out

    remove_user_from_room(email=other_email, room_id=room_id0, db_path=db_path)

    user, rooms = get_user(email=other_email, db_path=db_path)
    assert room_id0 not in rooms

    with pytest.raises(SystemExit) as excinfo:
        remove_user_from_room(email=other_email, room_id=room_id0, db_path=db_path)
    assert excinfo.value.code == 1
    output = capsys.readouterr().out
    assert "Room" in output
    assert room_id0 in output

    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        set_config(
            host=f"http://{host}",
            port=port,
            file_path=file_path,
            room_id=missing_room_id,
        )

        with pytest.raises(RuntimeError, match="Wrong username or password"):
            log_in(email, "wrongpassword")

        with pytest.raises(WebSocketUpgradeError):
            log_in(email, password)

        set_config(room_id=personal_room_id)

        log_in(email, password)
