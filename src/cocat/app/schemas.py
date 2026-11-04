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
    def create_update_dict(self):
        # fastapi-users uses this "safe" dict for self-service updates (PATCH /users/me);
        # room membership is the access control, so only admins may change it.
        update_dict = super().create_update_dict()
        update_dict.pop("rooms", None)
        return update_dict
