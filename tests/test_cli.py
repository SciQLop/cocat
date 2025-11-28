import keyring
import pytest
from fastapi_users.exceptions import UserAlreadyExists
from httpx_ws import WebSocketUpgradeError
from utils import get_credential, set_password

import cocat
from cocat import log_in, set_config
from cocat.cli import (
    add_user_to_room,
    create_user,
    get_user,
    remove_user_from_room,
)


def test_user(tmp_path, server, room_id, monkeypatch):
    host, port = server
    db_path = str(tmp_path / "test.db")
    file_path = tmp_path / "updates.y"
    email = "a@b.com"
    password = "pwd"
    room_id0 = room_id
    room_id1 = "room1"

    user = create_user(email=email, password=password, db_path=db_path)

    with pytest.raises(UserAlreadyExists):
        user = create_user(email=email, password=password, db_path=db_path)

    assert user.email == email
    assert user.rooms == ["a"]

    add_user_to_room(email=email, room_id=room_id0, db_path=db_path)
    add_user_to_room(email=email, room_id=room_id1, db_path=db_path)

    user = get_user(email=email, db_path=db_path)
    assert user.email == email
    assert set(user.rooms) == set([room_id0, room_id1, "a"])

    remove_user_from_room(email=email, room_id=room_id1, db_path=db_path)

    user = get_user(email=email, db_path=db_path)
    assert user.email == email
    assert set(user.rooms) == set([room_id0, "a"])

    with monkeypatch.context() as m:
        m.setattr(cocat.api, "save_on_exit", lambda: None)
        m.setattr(keyring, "get_credential", get_credential)
        m.setattr(keyring, "set_password", set_password)
        set_config(
            host=f"http://{host}",
            port=port,
            file_path=file_path,
            room_id=room_id1,
        )

        with pytest.raises(RuntimeError, match="Wrong username or password"):
            log_in(email, "wrongpassword")

        with pytest.raises(WebSocketUpgradeError):
            log_in(email, password)

        set_config(room_id=room_id0)

        log_in(email, password)
