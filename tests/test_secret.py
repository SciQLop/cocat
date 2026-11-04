import stat
import sys
from types import SimpleNamespace
from typing import Any, cast

import pytest

from cocat.app.secret import load_secret
from cocat.app.users import UserManager


def test_load_secret_creates_then_reuses(tmp_path):
    path = tmp_path / "s"

    secret = load_secret(path)

    assert secret
    assert load_secret(path) == secret
    assert path.exists()


def test_load_secret_env_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("COCAT_SECRET", "abc")
    path = tmp_path / "s"

    assert load_secret(path) == "abc"
    assert not path.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes only")
def test_load_secret_file_is_private(tmp_path):
    path = tmp_path / "s"

    load_secret(path)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_load_secret_strips_whitespace(tmp_path):
    path = tmp_path / "s"
    path.write_text("abc\n")

    assert load_secret(path) == "abc"


def test_load_secret_empty_file_raises(tmp_path):
    path = tmp_path / "s"
    path.write_text("\n")

    with pytest.raises(RuntimeError) as excinfo:
        load_secret(path)

    assert str(path) in str(excinfo.value)


def make_user_manager() -> UserManager:
    return UserManager(cast(Any, None))


@pytest.mark.anyio
async def test_forgot_password_does_not_log_token(capsys):
    user_manager = make_user_manager()
    user = SimpleNamespace(id=1)

    await user_manager.on_after_forgot_password(user, "TOKEN123", None)
    await user_manager.on_after_request_verify(user, "TOKEN123", None)

    assert "TOKEN123" not in capsys.readouterr().out
