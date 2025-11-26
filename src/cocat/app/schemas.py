import uuid

from fastapi_users import schemas
from pydantic import BaseModel


class CocatUser(BaseModel):
    rooms: list[str] = []


class UserRead(schemas.BaseUser[uuid.UUID], CocatUser):
    pass


class UserCreate(schemas.BaseUserCreate, CocatUser):
    pass


class UserUpdate(schemas.BaseUserUpdate, CocatUser):
    pass
