import sys
from pathlib import Path

import pytest

from cocat.app.app import StoredRoom
from cocat.app.db import User, get_db
from cocat.app.rooms import create_room, delete_room
from cocat.app.storage import remove_room_file, room_file

pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    # aiosqlite only runs on asyncio.
    return "asyncio"


def test_room_file_rejects_traversal_but_keeps_legacy_ids(tmp_path):
    for room_id in ("", ".", "..", "../x", "a/b", "a\\b", "a\0b"):
        with pytest.raises(ValueError):
            room_file(str(tmp_path), room_id)

    assert room_file(str(tmp_path), "o'brien") == (tmp_path / "o'brien.y").resolve()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX symlinks only")
def test_room_file_rejects_symlink_escape(tmp_path):
    outside = tmp_path / "outside.y"
    outside.touch()
    update_dir = tmp_path / "update_dir"
    update_dir.mkdir()
    (update_dir / "linked.y").symlink_to(outside)

    with pytest.raises(ValueError):
        room_file(str(update_dir), "linked")


def test_remove_room_file_is_idempotent(tmp_path):
    path = tmp_path / "lab.y"
    path.touch()

    remove_room_file(str(tmp_path), "lab")

    assert not path.exists()
    remove_room_file(str(tmp_path), "lab")


def test_remove_room_file_suppresses_permission_error(tmp_path, monkeypatch):
    path = tmp_path / "lab.y"
    path.touch()

    def locked(self: Path) -> None:
        raise PermissionError(self)

    monkeypatch.setattr(Path, "unlink", locked)

    remove_room_file(str(tmp_path), "lab")

    assert path.exists()


async def test_stored_room_removes_its_file_only_for_a_deleted_room(tmp_path):
    update_dir = tmp_path / "update_dir"
    update_dir.mkdir()
    db = get_db(str(tmp_path / "u.db"))
    await db.create_db_and_tables()
    async with db.async_session_maker() as session:
        owner = User(
            email="owner@x.org",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            is_verified=True,
        )
        session.add(owner)
        await session.commit()
        room = await create_room(session, owner, "Lab", room_id="lab")

    stored_room = StoredRoom(str(update_dir), db, "lab")
    path = room_file(str(update_dir), "lab")
    path.touch()

    await stored_room.remove_file_if_room_deleted()
    assert path.exists()

    async with db.async_session_maker() as session:
        await delete_room(session, room.id, owner)

    await stored_room.remove_file_if_room_deleted()
    assert not path.exists()
