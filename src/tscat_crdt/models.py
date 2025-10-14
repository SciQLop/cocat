from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventModel(BaseModel):
    uuid: UUID = Field(default_factory=lambda: uuid4())
    start: datetime
    stop: datetime
    author: str
    tags: dict[str, bool] = Field(default_factory=dict)
    products: dict[str, bool] = Field(default_factory=dict)
    rating: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class CatalogueModel(BaseModel):
    uuid: UUID = Field(default_factory=lambda: uuid4())
    name: str
    author: str
    tags: dict[str, bool] = Field(default_factory=dict)
    events: dict[str, bool] = Field(default_factory=dict)
    attributes: dict[str, Any] = Field(default_factory=dict)
