import re
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import ROLE_RANK, Membership, Role, Room, User

ROOM_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
PERSONAL_ROOM_NAME = "Personal"


class RoomError(Exception):
    pass


class NotFound(RoomError):
    pass


class Forbidden(RoomError):
    pass


class Conflict(RoomError):
    pass


def validate_room_id(room_id: str) -> str:
    if not ROOM_ID_PATTERN.fullmatch(room_id):
        raise ValueError(f"Invalid room id: {room_id!r}")
    return room_id


async def get_role(session: AsyncSession, room_id: str, user_id: UUID) -> Role | None:
    membership = await session.get(Membership, (room_id, user_id))
    return membership.role if membership is not None else None


async def require_role(
    session: AsyncSession, room_id: str, user: User, minimum: Role
) -> Role:
    role = await get_role(session, room_id, user.id)
    if role is None:
        raise NotFound(f"Room {room_id} not found")
    if ROLE_RANK[role] < ROLE_RANK[minimum]:
        raise Forbidden(f"Room {room_id} requires the {minimum.value} role")
    return role


async def create_room(
    session: AsyncSession, owner: User, name: str, room_id: str | None = None
) -> Room:
    room_id = validate_room_id(room_id) if room_id is not None else uuid4().hex
    if await session.get(Room, room_id) is not None:
        raise Conflict(f"Room {room_id} already exists")
    room = Room(id=room_id, name=name, created_by=owner.id)
    session.add(room)
    await _add_member(session, room_id, owner.id, Role.owner)
    await session.commit()
    return room


async def create_personal_room(session: AsyncSession, user: User) -> Room:
    return await create_room(session, user, PERSONAL_ROOM_NAME)


async def list_user_rooms(
    session: AsyncSession, user_id: UUID
) -> list[tuple[Room, Role]]:
    rows = await session.execute(
        select(Room, Membership.role)
        .join(Membership, Membership.room_id == Room.id)
        .where(Membership.user_id == user_id)
        .order_by(Room.name, Room.id)
    )
    return [(room, role) for room, role in rows]


async def _add_member(
    session: AsyncSession, room_id: str, user_id: UUID, role: Role
) -> Role:
    membership = await session.get(Membership, (room_id, user_id))
    if membership is None:
        session.add(Membership(room_id=room_id, user_id=user_id, role=role))
        return role
    if ROLE_RANK[role] > ROLE_RANK[membership.role]:
        membership.role = role
    return membership.role


async def add_member(
    session: AsyncSession, room_id: str, user_id: UUID, role: Role
) -> Role:
    member_role = await _add_member(session, room_id, user_id, role)
    await session.commit()
    return member_role


async def rename_room(
    session: AsyncSession, room_id: str, actor: User, name: str
) -> Room:
    await require_role(session, room_id, actor, Role.owner)
    room = await session.get_one(Room, room_id)
    room.name = name
    await session.commit()
    return room


async def delete_room(session: AsyncSession, room_id: str, actor: User) -> None:
    await require_role(session, room_id, actor, Role.owner)
    await session.execute(delete(Room).where(Room.id == room_id))
    await session.commit()


async def list_members(
    session: AsyncSession, room_id: str, actor: User
) -> list[tuple[User, Role]]:
    await require_role(session, room_id, actor, Role.viewer)
    rows = await session.execute(
        select(User, Membership.role)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.room_id == room_id)
        .order_by(User.email)
    )
    return [(user, role) for user, role in rows]


async def _membership(session: AsyncSession, room_id: str, user_id: UUID) -> Membership:
    membership = await session.get(Membership, (room_id, user_id))
    if membership is None:
        raise NotFound(f"User {user_id} is not a member of room {room_id}")
    return membership


async def set_member_role(
    session: AsyncSession, room_id: str, actor: User, member_id: UUID, role: Role
) -> None:
    await require_role(session, room_id, actor, Role.owner)
    membership = await _membership(session, room_id, member_id)
    if role is Role.owner or membership.role is Role.owner:
        raise Conflict("The owner keeps the owner role")
    membership.role = role
    await session.commit()


async def remove_member(
    session: AsyncSession, room_id: str, actor: User, member_id: UUID
) -> None:
    minimum = Role.viewer if member_id == actor.id else Role.owner
    await require_role(session, room_id, actor, minimum)
    membership = await _membership(session, room_id, member_id)
    if membership.role is Role.owner:
        raise Conflict("The owner cannot leave or be removed")
    await session.delete(membership)
    await session.commit()


async def _set_role(
    session: AsyncSession, room_id: str, user_id: UUID, role: Role
) -> None:
    membership = await _membership(session, room_id, user_id)
    membership.role = role


async def _owner_id(session: AsyncSession, room_id: str) -> UUID | None:
    return await session.scalar(
        select(Membership.user_id).where(
            Membership.room_id == room_id, Membership.role == Role.owner
        )
    )


async def transfer_ownership(
    session: AsyncSession, room_id: str, actor: User, new_owner_id: UUID
) -> None:
    await require_role(session, room_id, actor, Role.owner)
    await _membership(session, room_id, new_owner_id)
    await _set_role(session, room_id, actor.id, Role.editor)
    await _set_role(session, room_id, new_owner_id, Role.owner)
    await session.commit()


async def set_owner(session: AsyncSession, room_id: str, new_owner_id: UUID) -> None:
    await _membership(session, room_id, new_owner_id)
    previous_owner_id = await _owner_id(session, room_id)
    if previous_owner_id is not None and previous_owner_id != new_owner_id:
        await _set_role(session, room_id, previous_owner_id, Role.editor)
    await _set_role(session, room_id, new_owner_id, Role.owner)
    await session.commit()
