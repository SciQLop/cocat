from datetime import timedelta

import anyio
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cocat.app.db import Invitation, Membership, Role, User, get_db, utcnow
from cocat.app.invitations import (
    INVITATION_LIFETIME,
    InvitationPreview,
    _consume_invitation,
    accept_invitation,
    create_invitation,
    hash_token,
    list_invitations,
    preview_invitation,
    revoke_invitation,
)
from cocat.app.rooms import (
    Conflict,
    Forbidden,
    NotFound,
    add_member,
    create_room,
    get_role,
)

pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    # aiosqlite only runs on asyncio.
    return "asyncio"


async def make_user(session: AsyncSession, email: str) -> User:
    user = User(
        email=email,
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=True,
    )
    session.add(user)
    await session.commit()
    return user


@pytest.fixture()
async def session(tmp_path):
    db = get_db(str(tmp_path / "u.db"))
    await db.create_db_and_tables()
    async with db.async_session_maker() as session:
        yield session


@pytest.fixture()
async def owner(session: AsyncSession) -> User:
    return await make_user(session, "owner@x.org")


@pytest.fixture()
async def member(session: AsyncSession) -> User:
    return await make_user(session, "member@x.org")


def test_hash_token():
    assert hash_token("token") == hash_token("token")
    assert len(hash_token("token")) == 64
    assert hash_token("token") != hash_token("other")


async def test_link_invitation_accepted_by_anyone_until_max_uses(
    session, owner, member
):
    room = await create_room(session, owner, "Lab")
    invitation, token = await create_invitation(
        session, room.id, owner, Role.editor, max_uses=2
    )

    preview = await preview_invitation(session, token)
    assert preview == InvitationPreview(
        room_id=room.id,
        room_name="Lab",
        role=Role.editor,
        inviter_email="owner@x.org",
        expires_at=invitation.expires_at,
    )

    accepted_room = await accept_invitation(session, token, member)
    assert accepted_room.id == room.id
    assert await get_role(session, room.id, member.id) is Role.editor

    other = await make_user(session, "other@x.org")
    await accept_invitation(session, token, other)


async def test_used_up_invitation_refused_on_accept(session, owner, member):
    room = await create_room(session, owner, "Lab")
    _, token = await create_invitation(session, room.id, owner, Role.editor, max_uses=1)
    await accept_invitation(session, token, member)

    other = await make_user(session, "other@x.org")
    with pytest.raises(NotFound):
        await accept_invitation(session, token, other)
    with pytest.raises(NotFound):
        await preview_invitation(session, token)


async def test_email_invitation_only_for_that_email(session, owner, member):
    room = await create_room(session, owner, "Lab")
    invitation, token = await create_invitation(
        session, room.id, owner, Role.editor, email="invitee@x.org"
    )

    assert invitation.max_uses == 1
    assert invitation.expires_at - invitation.created_at == INVITATION_LIFETIME
    with pytest.raises(Forbidden):
        await accept_invitation(session, token, member)
    await session.refresh(invitation)
    assert invitation.uses == 0

    invitee = await make_user(session, "Invitee@X.org")
    await accept_invitation(session, token, invitee)
    assert await get_role(session, room.id, invitee.id) is Role.editor


async def test_expired_invitation_refused_on_accept(session, owner, member):
    room = await create_room(session, owner, "Lab")
    _, token = await create_invitation(
        session, room.id, owner, Role.editor, expires_in=timedelta(seconds=-1)
    )

    with pytest.raises(NotFound):
        await accept_invitation(session, token, member)
    with pytest.raises(NotFound):
        await preview_invitation(session, token)


async def test_revoked_invitation_refused_on_accept(session, owner, member):
    room = await create_room(session, owner, "Lab")
    invitation, token = await create_invitation(session, room.id, owner, Role.editor)

    await revoke_invitation(session, room.id, owner, invitation.id)

    with pytest.raises(NotFound):
        await accept_invitation(session, token, member)
    with pytest.raises(NotFound):
        await preview_invitation(session, token)


async def test_unknown_token_is_not_found(session):
    with pytest.raises(NotFound):
        await preview_invitation(session, "unknown")


async def test_token_not_stored_in_clear(session, owner):
    room = await create_room(session, owner, "Lab")
    invitation, token = await create_invitation(session, room.id, owner, Role.editor)

    await session.refresh(invitation)
    stored = [
        str(getattr(invitation, column.name)) for column in Invitation.__table__.columns
    ]

    assert all(token != value for value in stored)


async def test_accept_does_not_downgrade_existing_owner(session, owner):
    room = await create_room(session, owner, "Lab")
    _, token = await create_invitation(session, room.id, owner, Role.editor)

    await accept_invitation(session, token, owner)

    assert await get_role(session, room.id, owner.id) is Role.owner


async def test_non_owner_cannot_invite_and_owner_role_is_refused(
    session, owner, member
):
    room = await create_room(session, owner, "Lab")

    await add_member(session, room.id, member.id, Role.editor)

    with pytest.raises(Forbidden):
        await create_invitation(session, room.id, member, Role.editor)
    with pytest.raises(Conflict):
        await create_invitation(session, room.id, owner, Role.owner)


async def test_list_hides_expired_and_revoked(session, owner):
    room = await create_room(session, owner, "Lab")
    first, _ = await create_invitation(session, room.id, owner, Role.editor)
    expired, _ = await create_invitation(
        session, room.id, owner, Role.editor, expires_in=timedelta(seconds=-1)
    )
    revoked, _ = await create_invitation(session, room.id, owner, Role.editor)
    await revoke_invitation(session, room.id, owner, revoked.id)
    second, _ = await create_invitation(session, room.id, owner, Role.editor)

    listed = await list_invitations(session, room.id, owner)

    assert [invitation.id for invitation in listed] == [second.id, first.id]
    assert expired.id not in {invitation.id for invitation in listed}


async def test_revoke_unknown_or_foreign_invitation_is_not_found(session, owner):
    room = await create_room(session, owner, "Lab")
    other_room = await create_room(session, owner, "Other")
    invitation, _ = await create_invitation(session, room.id, owner, Role.editor)

    with pytest.raises(NotFound):
        await revoke_invitation(session, other_room.id, owner, invitation.id)
    with pytest.raises(NotFound):
        await revoke_invitation(session, room.id, owner, invitation.id + 1000)


async def test_consume_invitation_refuses_second_use(session, owner):
    room = await create_room(session, owner, "Lab")
    invitation, _ = await create_invitation(
        session, room.id, owner, Role.editor, max_uses=1
    )

    await _consume_invitation(session, invitation.id, utcnow())
    with pytest.raises(NotFound):
        await _consume_invitation(session, invitation.id, utcnow())


async def test_concurrent_accept_single_use(tmp_path):
    db = get_db(str(tmp_path / "u.db"))
    await db.create_db_and_tables()
    async with db.async_session_maker() as setup:
        owner = await make_user(setup, "owner@x.org")
        alice = await make_user(setup, "alice@x.org")
        bob = await make_user(setup, "bob@x.org")
        room = await create_room(setup, owner, "Lab")
        invitation, token = await create_invitation(
            setup, room.id, owner, Role.editor, max_uses=1
        )

    results: list[str] = []

    async def accept(user_id):
        async with db.async_session_maker() as session:
            user = await session.get_one(User, user_id)
            try:
                await accept_invitation(session, token, user)
            except NotFound:
                results.append("refused")
            else:
                results.append("accepted")

    async with anyio.create_task_group() as task_group:
        task_group.start_soon(accept, alice.id)
        task_group.start_soon(accept, bob.id)

    assert sorted(results) == ["accepted", "refused"]
    async with db.async_session_maker() as session:
        uses = await session.scalar(
            select(Invitation.uses).where(Invitation.id == invitation.id)
        )
        members = await session.scalar(
            select(func.count())
            .select_from(Membership)
            .where(Membership.room_id == room.id)
        )
    assert uses == 1
    assert members == 2
