"""rooms, memberships and invitations

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-04

"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

ROLE = sa.Enum("owner", "editor", "viewer", name="role")

USER = sa.table(
    "user",
    sa.column("id", sa.CHAR(36)),
    sa.column("email", sa.String),
    sa.column("rooms", sa.JSON),
)
ROOM = sa.table(
    "room",
    sa.column("id", sa.String),
    sa.column("name", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("created_by", sa.CHAR(36)),
)
MEMBERSHIP = sa.table(
    "membership",
    sa.column("room_id", sa.String),
    sa.column("user_id", sa.CHAR(36)),
    sa.column("role", sa.String),
    sa.column("joined_at", sa.DateTime),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def upgrade() -> None:
    bind = op.get_bind()
    _create_missing_tables(bind)
    _migrate_user_rooms(bind)


def downgrade() -> None:
    op.drop_table("invitation")
    op.drop_table("membership")
    op.drop_table("room")


def _create_missing_tables(bind: sa.Connection) -> None:
    inspector = sa.inspect(bind)
    if not inspector.has_table("room"):
        op.create_table(
            "room",
            sa.Column("id", sa.String(255), nullable=False),
            sa.Column("name", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("created_by", sa.CHAR(36), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        )
    if not inspector.has_table("membership"):
        op.create_table(
            "membership",
            sa.Column("room_id", sa.String(255), nullable=False),
            sa.Column("user_id", sa.CHAR(36), nullable=False),
            sa.Column("role", ROLE, nullable=False),
            sa.Column("joined_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("room_id", "user_id"),
            sa.ForeignKeyConstraint(["room_id"], ["room.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        )
    if not inspector.has_table("invitation"):
        op.create_table(
            "invitation",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("room_id", sa.String(255), nullable=False),
            sa.Column("role", ROLE, nullable=False),
            sa.Column("email", sa.String(320), nullable=True),
            sa.Column("created_by", sa.CHAR(36), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked", sa.Boolean(), nullable=False),
            sa.Column("max_uses", sa.Integer(), nullable=True),
            sa.Column("uses", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("token_hash"),
            sa.ForeignKeyConstraint(["room_id"], ["room.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["created_by"], ["user.id"], ondelete="SET NULL"),
        )


def _migrate_user_rooms(bind: sa.Connection) -> None:
    users = bind.execute(sa.select(USER.c.id, USER.c.email, USER.c.rooms)).all()
    members: dict[str, list[tuple[str, str]]] = {}
    for user_id, email, rooms in users:
        if not _is_room_list(rooms):
            print(f"warning: skipping the rooms of {email}: not a JSON list of strings")
            continue
        for room_id in rooms:
            bind.execute(
                sqlite_insert(ROOM)
                .values(id=room_id, name=room_id, created_at=utcnow())
                .on_conflict_do_nothing()
            )
            bind.execute(
                sqlite_insert(MEMBERSHIP)
                .values(
                    room_id=room_id, user_id=user_id, role="editor", joined_at=utcnow()
                )
                .on_conflict_do_nothing()
            )
            members.setdefault(room_id, []).append((user_id, email))
    for room_id, room_members in members.items():
        _promote_owner(bind, room_id, room_members)


def _is_room_list(rooms: object) -> bool:
    return isinstance(rooms, list) and all(isinstance(room, str) for room in rooms)


def _promote_owner(
    bind: sa.Connection, room_id: str, members: list[tuple[str, str]]
) -> None:
    if _has_owner(bind, room_id):
        return
    owner_id = _pick_owner(room_id, members)
    bind.execute(
        sa.update(MEMBERSHIP)
        .where(MEMBERSHIP.c.room_id == room_id, MEMBERSHIP.c.user_id == owner_id)
        .values(role="owner")
    )
    bind.execute(
        sa.update(ROOM).where(ROOM.c.id == room_id).values(created_by=owner_id)
    )


def _has_owner(bind: sa.Connection, room_id: str) -> bool:
    owner = bind.execute(
        sa.select(MEMBERSHIP.c.user_id).where(
            MEMBERSHIP.c.room_id == room_id, MEMBERSHIP.c.role == "owner"
        )
    ).scalar()
    return owner is not None


def _pick_owner(room_id: str, members: list[tuple[str, str]]) -> str:
    by_email = sorted(members, key=lambda member: member[1])
    matches = [member for member in by_email if member[1].split("@")[0] == room_id]
    if len(matches) > 1:
        emails = ", ".join(email for _, email in matches)
        print(
            f"room '{room_id}' was shared by {emails}; owner set to {matches[0][1]}"
            " (change with: cocat set-room-owner)"
        )
    owner = matches[0] if matches else by_email[0]
    return owner[0]
