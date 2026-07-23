# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""‌⁠‍{{display_name}} ORM models.

Tables:
    oe_{{module_short}}_item — stub entity to demonstrate the pattern.

Every table name MUST start with ``oe_{{module_short}}_`` so a future
``alembic downgrade --module`` knows which rows belong to whom.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID, Base


class Item(Base):
    """‌⁠‍A generic item owned by a project.

    Replace this with your real domain entity. ``Base`` already gives
    you ``id`` (UUID PK), ``created_at`` and ``updated_at`` — do not
    redeclare them.
    """

    __tablename__ = "oe_{{module_short}}_item"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # Project ownership is the default scoping pattern across OpenEstimate.
    # Drop this column if your module is project-agnostic (rare).
    project_id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        ForeignKey("oe_projects_project.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Free-form metadata — handy escape hatch while the module is still
    # shaping its real schema. Promote frequently-queried keys to real
    # columns once they stabilise.
    # metadata_: Mapped[dict | None] = mapped_column(JSON, nullable=True)
