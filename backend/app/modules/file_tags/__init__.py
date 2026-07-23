# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File tags module (W4).

Project-scoped polymorphic tags for every file kind in the file manager.
A tag belongs to a single project and can be assigned to documents,
sheets, photos, BIM models, DWG drawings, takeoffs, reports, or markups
via the ``(file_kind, file_id)`` polymorphic anchor on
``oe_file_tag_assignment``.

Why project-scoped?
    Two unrelated projects can both have a "structural" tag without
    bleeding into each other's tag picker. The unique constraint on
    ``(project_id, name)`` enforces this.

Why a slug (``name``) + display label (``display_name``)?
    Slug is used for URLs, filters, and dedupe. Display label preserves
    case + punctuation for UI ("Mechanical & Plumbing" → ``mech_and_plumbing``).
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.file_tags.permissions import register_file_tags_permissions

    register_file_tags_permissions()
