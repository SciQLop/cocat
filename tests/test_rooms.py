import pytest
from conftest import make_orm_user
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from cocat.app.db import Membership, Role, Room, User
from cocat.app.rooms import (
    Conflict,
    Forbidden,
    NotFound,
    add_member,
    create_personal_room,
    create_room,
    delete_room,
    get_role,
    list_members,
    list_user_rooms,
    remove_member,
    rename_room,
    require_role,
    set_member_role,
    set_owner,
    transfer_ownership,
    validate_room_id,
)

pytestmark = pytest.mark.anyio


@pytest.fixture()
def anyio_backend() -> str:
    # aiosqlite only runs on asyncio.
    return "asyncio"


@pytest.fixture()
async def owner(session: AsyncSession) -> User:
    return await make_orm_user(session, "owner@x.org")


@pytest.fixture()
async def editor(session: AsyncSession) -> User:
    return await make_orm_user(session, "editor@x.org")


@pytest.fixture()
async def stranger(session: AsyncSession) -> User:
    return await make_orm_user(session, "stranger@x.org")


def test_validate_room_id():
    for room_id in ["john", "lab_A-2", "a" * 64]:
        assert validate_room_id(room_id) == room_id

    for room_id in ["", "..", "../x", ".hidden", "a/b", "o'brien", "a" * 65]:
        with pytest.raises(ValueError):
            validate_room_id(room_id)


async def test_create_room_and_personal_room(session, owner):
    room = await create_room(session, owner, "Lab", room_id="lab_A-2")
    personal = await create_personal_room(session, owner)

    assert room.name == "Lab"
    assert room.created_by == owner.id
    assert personal.name == "Personal"
    assert personal.id != room.id
    assert await get_role(session, personal.id, owner.id) is Role.owner


async def test_create_room_conflict(session, owner):
    await create_room(session, owner, "Lab", room_id="lab")

    with pytest.raises(Conflict):
        await create_room(session, owner, "Other", room_id="lab")


async def test_create_room_validates_explicit_id(session, owner):
    with pytest.raises(ValueError):
        await create_room(session, owner, "Lab", room_id="../x")


async def test_get_role(session, owner, stranger):
    room = await create_room(session, owner, "Lab")

    assert await get_role(session, room.id, owner.id) is Role.owner
    assert await get_role(session, room.id, stranger.id) is None


async def test_unknown_room_and_non_member_both_not_found(session, owner, stranger):
    room = await create_room(session, owner, "Lab")

    with pytest.raises(NotFound):
        await require_role(session, "missing", owner, Role.viewer)
    with pytest.raises(NotFound):
        await require_role(session, room.id, stranger, Role.viewer)

    assert await require_role(session, room.id, owner, Role.viewer) is Role.owner


async def test_editor_rename_forbidden(session, owner, editor):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    with pytest.raises(Forbidden):
        await rename_room(session, room.id, editor, "Renamed")

    renamed = await rename_room(session, room.id, owner, "Renamed")
    assert renamed.name == "Renamed"


async def test_list_user_rooms_sorted(session, owner):
    await create_room(session, owner, "B")
    await create_room(session, owner, "A")

    rooms = await list_user_rooms(session, owner.id)

    assert [(room.name, role) for room, role in rooms] == [
        ("A", Role.owner),
        ("B", Role.owner),
    ]


async def test_add_member_keeps_higher_role(session, owner, editor):
    room = await create_room(session, owner, "Lab")

    assert await add_member(session, room.id, editor.id, Role.editor) is Role.editor
    assert await add_member(session, room.id, editor.id, Role.viewer) is Role.editor
    assert await add_member(session, room.id, editor.id, Role.owner) is Role.owner
    assert await add_member(session, room.id, editor.id, Role.owner) is Role.owner


async def test_list_members_sorted_by_email(session, owner, editor):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    assert await list_members(session, room.id, editor) == [
        (editor, Role.editor),
        (owner, Role.owner),
    ]


async def test_set_role_on_non_member_is_not_found(session, owner, stranger):
    room = await create_room(session, owner, "Lab")

    with pytest.raises(NotFound):
        await set_member_role(session, room.id, owner, stranger.id, Role.editor)

    assert await get_role(session, room.id, stranger.id) is None


async def test_set_role_owner_refused(session, owner, editor):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    with pytest.raises(Conflict):
        await set_member_role(session, room.id, owner, editor.id, Role.owner)
    with pytest.raises(Conflict):
        await set_member_role(session, room.id, owner, owner.id, Role.editor)

    await set_member_role(session, room.id, owner, editor.id, Role.viewer)
    assert await get_role(session, room.id, editor.id) is Role.viewer


async def test_owner_cannot_leave(session, owner):
    room = await create_room(session, owner, "Lab")

    with pytest.raises(Conflict):
        await remove_member(session, room.id, owner, owner.id)


async def test_editor_can_leave(session, owner, editor):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    await remove_member(session, room.id, editor, editor.id)

    assert await get_role(session, room.id, editor.id) is None


async def test_editor_cannot_remove_others(session, owner, editor):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    with pytest.raises(Forbidden):
        await remove_member(session, room.id, editor, owner.id)


async def test_owner_can_remove_member_and_non_member_is_not_found(
    session, owner, editor, stranger
):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    await remove_member(session, room.id, owner, editor.id)

    assert await get_role(session, room.id, editor.id) is None
    with pytest.raises(NotFound):
        await remove_member(session, room.id, owner, stranger.id)


async def test_transfer_ownership_swaps_roles(session, owner, editor, stranger):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    await transfer_ownership(session, room.id, owner, editor.id)

    assert await get_role(session, room.id, editor.id) is Role.owner
    assert await get_role(session, room.id, owner.id) is Role.editor
    with pytest.raises(NotFound):
        await transfer_ownership(session, room.id, editor, stranger.id)


async def test_set_owner_swaps_roles(session, owner, editor, stranger):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    await set_owner(session, room.id, editor.id)

    assert await get_role(session, room.id, editor.id) is Role.owner
    assert await get_role(session, room.id, owner.id) is Role.editor
    with pytest.raises(NotFound):
        await set_owner(session, room.id, stranger.id)


async def test_delete_room_removes_memberships(session, owner, editor):
    room = await create_room(session, owner, "Lab")
    await add_member(session, room.id, editor.id, Role.editor)

    await delete_room(session, room.id, owner)

    rooms = select(func.count()).select_from(Room).where(Room.id == room.id)
    memberships = (
        select(func.count())
        .select_from(Membership)
        .where(Membership.room_id == room.id)
    )
    assert await session.scalar(rooms) == 0
    assert await session.scalar(memberships) == 0
