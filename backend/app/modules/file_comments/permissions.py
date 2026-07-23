# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Comments module permission definitions.

Three permissions:

* ``file_comments.read``    - list / get threads (every project member;
                              VIEWER tier).
* ``file_comments.write``   - post / edit / delete one's own comment
                              (EDITOR tier).
* ``file_comments.resolve`` - mark a thread resolved or reopen it
                              (EDITOR tier; reopening a resolved thread
                              is the same gate so reviewers can correct
                              an over-eager resolve).
"""

from app.core.permissions import Role, permission_registry


def register_file_comments_permissions() -> None:
    """Register permissions for the file_comments module."""
    permission_registry.register_module_permissions(
        "file_comments",
        {
            "file_comments.read": Role.VIEWER,
            "file_comments.write": Role.EDITOR,
            "file_comments.resolve": Role.EDITOR,
        },
    )
