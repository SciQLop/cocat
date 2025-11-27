import uuid

from fastapi_users import schemas
from pydantic import BaseModel


class RoomUsers(BaseModel):
    users: list[str] = []


class UserRooms(BaseModel):
    rooms: list[str] = []


class UserRead(schemas.BaseUser[uuid.UUID], UserRooms):
    pass


class UserCreate(schemas.BaseUserCreate, UserRooms):
    pass


class UserUpdate(schemas.BaseUserUpdate, UserRooms):
    pass
