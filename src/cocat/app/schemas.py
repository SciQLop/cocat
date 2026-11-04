import uuid
from datetime import datetime
from typing import Literal

from fastapi_users import schemas
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .db import Role


class RoomUsers(BaseModel):
    users: list[str] = []


class UserRooms(BaseModel):
    rooms: list[str] = []


class UserRead(schemas.BaseUser[uuid.UUID], UserRooms):
    pass


class UserCreate(schemas.BaseUserCreate, UserRooms):
    pass


class UserUpdate(schemas.BaseUserUpdate, UserRooms):
    def create_update_dict(self):
        # fastapi-users uses this "safe" dict for self-service updates (PATCH /users/me);
        # room membership is the access control, so only admins may change it.
        update_dict = super().create_update_dict()
        update_dict.pop("rooms", None)
        return update_dict


class RoomOut(BaseModel):
    id: str
    name: str
    role: Role


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class RoomRename(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    role: Role


class RoleUpdate(BaseModel):
    role: Literal["editor"]


class OwnerTransfer(BaseModel):
    user_id: uuid.UUID


class InvitationCreate(BaseModel):
    email: EmailStr | None = None
    role: Literal["editor"] = "editor"
    expires_in_days: int = Field(14, ge=1, le=90)
    max_uses: int | None = Field(None, ge=1)


class InvitationCreated(BaseModel):
    id: int
    token: str


class InvitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    role: Role
    expires_at: datetime
    uses: int
    max_uses: int | None


class InvitationToken(BaseModel):
    token: str


class InvitationPreviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    room_id: str
    room_name: str
    role: Role
    inviter_email: str | None
    expires_at: datetime
