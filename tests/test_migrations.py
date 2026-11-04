import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import anyio
from alembic import command
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine

from cocat.app.db import get_db, migration_config, utcnow

LEGACY_SCHEMA = """
CREATE TABLE user (
    rooms JSON NOT NULL,
    id CHAR(36) NOT NULL,
    email VARCHAR(320) NOT NULL,
    hashed_password VARCHAR(1024) NOT NULL,
    is_active BOOLEAN NOT NULL,
    is_superuser BOOLEAN NOT NULL,
    is_verified BOOLEAN NOT NULL,
    PRIMARY KEY (id)
);
CREATE UNIQUE INDEX ix_user_email ON user (email);
CREATE TABLE accesstoken (
    user_id CHAR(36) NOT NULL,
    token VARCHAR(43) NOT NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (token),
    FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE cascade
);
CREATE INDEX ix_accesstoken_created_at ON accesstoken (created_at);
"""


def make_legacy_db(path: Path, users: dict[str, list[str] | str]) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(LEGACY_SCHEMA)
        connection.executemany(
            "INSERT INTO user"
            " (id, email, hashed_password, is_active, is_superuser, is_verified,"
            " rooms)"
            " VALUES (?, ?, ?, 1, 0, 0, ?)",
            [
                (
                    str(uuid4()),
                    email,
                    "hashed",
                    rooms if isinstance(rooms, str) else json.dumps(rooms),
                )
                for email, rooms in users.items()
            ],
        )


def read_rows(path: Path, query: str) -> list[tuple]:
    with sqlite3.connect(path) as connection:
        return connection.execute(query).fetchall()


def table_names(path: Path) -> set[str]:
    with sqlite3.connect(path) as connection:
        rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        return {name for (name,) in rows}


def create_tables(path: Path) -> None:
    async def create() -> None:
        await get_db(str(path)).create_db_and_tables()

    anyio.run(create)


def head_revision() -> str:
    head = ScriptDirectory.from_config(migration_config()).get_current_head()
    assert head is not None
    return head


def test_creates_tables_when_file_already_exists(tmp_path):
    db_path = tmp_path / "u.db"
    db_path.touch()

    create_tables(db_path)

    assert {
        "user",
        "accesstoken",
        "alembic_version",
        "room",
        "membership",
        "invitation",
    } <= table_names(db_path)


def test_stamps_legacy_db(tmp_path):
    db_path = tmp_path / "u.db"
    make_legacy_db(db_path, {"john@a.org": ["x"]})

    create_tables(db_path)

    with sqlite3.connect(db_path) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()[0]
        emails = [email for (email,) in connection.execute("SELECT email FROM user")]
    assert version == head_revision()
    assert emails == ["john@a.org"]


def test_is_idempotent(tmp_path):
    db_path = tmp_path / "u.db"

    async def create_twice() -> None:
        db = get_db(str(db_path))
        await db.create_db_and_tables()
        await db.create_db_and_tables()

    anyio.run(create_twice)

    assert "user" in table_names(db_path)


def test_downgrade_to_base_drops_tables(tmp_path):
    db_path = tmp_path / "u.db"
    migrate_legacy_rooms(db_path)

    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as connection:
        command.downgrade(migration_config(connection), "base")

    assert not {
        "user",
        "accesstoken",
        "room",
        "membership",
        "invitation",
    } & table_names(db_path)


def test_utcnow_is_naive_utc():
    now = utcnow()

    assert now.tzinfo is None
    assert (
        abs((datetime.now(timezone.utc).replace(tzinfo=None) - now).total_seconds()) < 5
    )


LEGACY_ROOMS: dict[str, list[str] | str] = {
    "john@a.org": ["john", "shared"],
    "john@b.org": ["john"],
    "mary@c.org": ["shared"],
    "bad@d.org": '"oops"',
}

MEMBERS_SQL = (
    "SELECT m.room_id, u.email, m.role FROM membership m"
    " JOIN user u ON u.id = m.user_id ORDER BY m.room_id, u.email"
)


def migrate_legacy_rooms(path: Path) -> None:
    make_legacy_db(path, LEGACY_ROOMS)
    create_tables(path)


def test_rooms_migrated_with_owners(tmp_path):
    db_path = tmp_path / "u.db"

    migrate_legacy_rooms(db_path)

    assert read_rows(db_path, MEMBERS_SQL) == [
        ("john", "john@a.org", "owner"),
        ("john", "john@b.org", "editor"),
        ("shared", "john@a.org", "owner"),
        ("shared", "mary@c.org", "editor"),
    ]
    assert read_rows(
        db_path,
        "SELECT id, (SELECT email FROM user WHERE user.id = room.created_by)"
        " FROM room ORDER BY id",
    ) == [("john", "john@a.org"), ("shared", "john@a.org")]


def test_prefix_collision_reported(tmp_path, capsys):
    migrate_legacy_rooms(tmp_path / "u.db")

    assert "room 'john' was shared by john@a.org, john@b.org" in capsys.readouterr().out


def test_malformed_rooms_skipped(tmp_path, capsys):
    db_path = tmp_path / "u.db"

    migrate_legacy_rooms(db_path)

    assert "bad@d.org" in capsys.readouterr().out
    assert read_rows(
        db_path,
        "SELECT COUNT(*) FROM membership m JOIN user u ON u.id = m.user_id"
        " WHERE u.email = 'bad@d.org'",
    ) == [(0,)]


PARTIAL_ROOM_TABLE = """
CREATE TABLE room (
    id VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL,
    created_by CHAR(36),
    PRIMARY KEY (id)
);
"""


def test_migration_resumes_after_partial_run(tmp_path):
    db_path = tmp_path / "u.db"
    make_legacy_db(db_path, {"john@a.org": ["john"]})
    with sqlite3.connect(db_path) as connection:
        connection.executescript(PARTIAL_ROOM_TABLE)

    create_tables(db_path)

    assert read_rows(db_path, "SELECT role FROM membership") == [("owner",)]
    assert {"membership", "invitation"} <= table_names(db_path)


def test_migration_is_safe_to_rerun_after_a_crash(tmp_path):
    db_path = tmp_path / "u.db"
    migrate_legacy_rooms(db_path)
    before = read_rows(db_path, MEMBERS_SQL)

    with sqlite3.connect(db_path) as connection:
        connection.execute("DELETE FROM alembic_version")

    create_tables(db_path)

    assert read_rows(db_path, MEMBERS_SQL) == before


def test_deleting_user_cascades_memberships(tmp_path):
    db_path = tmp_path / "u.db"
    migrate_legacy_rooms(db_path)

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("DELETE FROM user WHERE email = 'john@a.org'")

    assert read_rows(db_path, MEMBERS_SQL) == [
        ("john", "john@b.org", "editor"),
        ("shared", "mary@c.org", "editor"),
    ]
    assert read_rows(db_path, "SELECT created_by FROM room") == [(None,), (None,)]


def test_migrating_to_head_keeps_memberships(tmp_path):
    db_path = tmp_path / "u.db"
    migrate_legacy_rooms(db_path)
    before = read_rows(db_path, MEMBERS_SQL)

    create_tables(db_path)

    assert read_rows(db_path, MEMBERS_SQL) == before
