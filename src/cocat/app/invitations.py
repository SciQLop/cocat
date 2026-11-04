import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from .db import Invitation, Role, Room, User, utcnow
from .rooms import Conflict, Forbidden, NotFound, _add_member, require_role

INVITATION_LIFETIME = timedelta(days=14)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class InvitationPreview:
    room_id: str
    room_name: str
    role: Role
    inviter_email: str | None
    expires_at: datetime


def _valid_invitation_filter(now: datetime) -> ColumnElement[bool]:
    return and_(
        Invitation.revoked.is_(False),
        Invitation.expires_at > now,
        or_(Invitation.max_uses.is_(None), Invitation.uses < Invitation.max_uses),
    )


async def create_invitation(
    session: AsyncSession,
    room_id: str,
    actor: User,
    role: Role,
    email: str | None = None,
    expires_in: timedelta = INVITATION_LIFETIME,
    max_uses: int | None = None,
) -> tuple[Invitation, str]:
    await require_role(session, room_id, actor, Role.owner)
    if role is Role.owner:
        raise Conflict("An invitation cannot grant the owner role")
    token = secrets.token_urlsafe(32)
    now = utcnow()
    invitation = Invitation(
        token_hash=hash_token(token),
        room_id=room_id,
        role=role,
        email=email,
        created_by=actor.id,
        created_at=now,
        expires_at=now + expires_in,
        max_uses=1 if email is not None else max_uses,
    )
    session.add(invitation)
    await session.commit()
    return invitation, token


async def preview_invitation(session: AsyncSession, token: str) -> InvitationPreview:
    row = (
        await session.execute(
            select(Invitation, Room.name, User.__table__.c.email)
            .join(Room, Room.id == Invitation.room_id)
            .outerjoin(User, User.__table__.c.id == Invitation.created_by)
            .where(
                Invitation.token_hash == hash_token(token),
                _valid_invitation_filter(utcnow()),
            )
        )
    ).first()
    if row is None:
        raise NotFound("Invitation not found")
    invitation, room_name, inviter_email = row
    return InvitationPreview(
        room_id=invitation.room_id,
        room_name=room_name,
        role=invitation.role,
        inviter_email=inviter_email,
        expires_at=invitation.expires_at,
    )


async def _consume_invitation(
    session: AsyncSession, invitation_id: int, now: datetime
) -> None:
    used = cast(
        CursorResult,
        await session.execute(
            update(Invitation)
            .where(Invitation.id == invitation_id, _valid_invitation_filter(now))
            .values(uses=Invitation.uses + 1)
        ),
    )
    if used.rowcount != 1:
        raise NotFound("Invitation not found")


async def accept_invitation(
    session: AsyncSession, token: str, user: User
) -> tuple[Room, Role]:
    now = utcnow()
    invitation = await session.scalar(
        select(Invitation).where(
            Invitation.token_hash == hash_token(token),
            _valid_invitation_filter(now),
        )
    )
    if invitation is None:
        raise NotFound("Invitation not found")
    if invitation.email is not None and invitation.email.lower() != user.email.lower():
        raise Forbidden("This invitation is for another email address")
    await _consume_invitation(session, invitation.id, now)
    role = await _add_member(session, invitation.room_id, user.id, invitation.role)
    await session.commit()
    return await session.get_one(Room, invitation.room_id), role


async def list_invitations(
    session: AsyncSession, room_id: str, actor: User
) -> list[Invitation]:
    await require_role(session, room_id, actor, Role.owner)
    rows = await session.scalars(
        select(Invitation)
        .where(
            Invitation.room_id == room_id,
            _valid_invitation_filter(utcnow()),
        )
        .order_by(Invitation.created_at.desc(), Invitation.id.desc())
    )
    return list(rows)


async def revoke_invitation(
    session: AsyncSession, room_id: str, actor: User, invitation_id: int
) -> None:
    await require_role(session, room_id, actor, Role.owner)
    invitation = await session.get(Invitation, invitation_id)
    if invitation is None or invitation.room_id != room_id:
        raise NotFound(f"Invitation {invitation_id} not found")
    invitation.revoked = True
    await session.commit()
