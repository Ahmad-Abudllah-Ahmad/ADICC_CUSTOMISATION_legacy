"""Optional Pydantic base for response schemas.

The platform convention is that a "read" schema sets
``model_config = ConfigDict(from_attributes=True)`` so it can be built straight
from an ORM instance with ``ReadSchema.model_validate(orm_row)``. ``ORMModel``
bakes that one line in so a read schema can just subclass it. This is optional
sugar. A plain ``pydantic.BaseModel`` with the config set by hand is equally
valid and is what the module template uses.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

__all__ = ["ORMModel"]


class ORMModel(BaseModel):
    """Pydantic base with ``from_attributes=True`` preset for ORM reads.

    Subclass this for response schemas that are validated from ORM instances:

        from uuid import UUID

        from oe_sdk import ORMModel

        class ItemRead(ORMModel):
            id: UUID
            name: str
    """

    model_config = ConfigDict(from_attributes=True)
