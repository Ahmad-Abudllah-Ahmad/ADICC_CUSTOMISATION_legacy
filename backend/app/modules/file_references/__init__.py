# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File References module.

Two responsibilities sharing one table-prefix:

* **ISO 19650 naming validation** - checks a filename against the
  ``Project-Originator-Volume-Level-Type-Role-Number[-Status][-Revision]``
  rule set and persists per-file violations so the file manager can
  surface a "fix me" banner.

* **Cross-entity linking** - a generic many-to-one anchor that lets a
  file (any file_kind) be referenced from an RFI / Issue / Task /
  Submittal etc. The "Referenced in N RFIs" chip in the file preview
  pane is backed by this table.

Both surfaces share the module so the same permission cluster gates
naming sweeps and linking flows.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.file_references.permissions import (
        register_file_references_permissions,
    )

    register_file_references_permissions()
