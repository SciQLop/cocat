from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventModel(BaseModel):
    """
    The [pydantic](https://docs.pydantic.dev) model for event validation.
    """
    uuid: UUID = Field(default_factory=lambda: uuid4())
    start: datetime
    stop: datetime
    author: str
    tags: list[str] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    rating: int | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class CatalogueModel(BaseModel):
    """
    The [pydantic](https://docs.pydantic.dev) model for catalogue validation.
    """
    uuid: UUID = Field(default_factory=lambda: uuid4())
    name: str
    author: str
    tags: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
