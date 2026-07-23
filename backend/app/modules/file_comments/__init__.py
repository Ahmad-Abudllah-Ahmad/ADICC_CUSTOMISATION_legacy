# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Comments module.

Threaded comments + PDF pin annotations attachable to any file kind
exposed through ``/files`` (document, photo, sheet, bim_model,
dwg_drawing, takeoff, report, markup).

Tables:
    * ``oe_file_comment``         - polymorphic threaded comment
    * ``oe_file_comment_mention`` - @mention resolution rows
"""


async def on_startup() -> None:
    """Module startup hook - register permissions."""
    from app.modules.file_comments.permissions import register_file_comments_permissions

    register_file_comments_permissions()
