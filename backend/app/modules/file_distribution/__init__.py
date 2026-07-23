# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""File Distribution module - cross-project search + distribution lists.

Two sub-features sharing the ``/api/v1/file-distribution`` namespace
because they are conceptually two halves of the same "distribute a
file to the right humans" workflow.

Sub-A: Cross-project search
    ``GET /search/`` performs a ranked search over file canonical_name
    across every project the caller can read, optionally augmenting
    the match with content-text snippets when the ``file_search``
    module is installed. ``file_search`` is a soft optional dependency
    - its absence simply collapses search to canonical_name.

Sub-B: Distribution lists & subscriptions
    Named recipient groups (with optional roles like ``for_review`` /
    ``fyi`` / ``for_construction``) that a user re-uses when sharing,
    emailing or transmitting drawings. Per-project or global to the
    owner. Subscriptions let a user (or an external email address)
    auto-receive notifications whenever a file of a given kind
    changes in a project.
"""


async def on_startup() -> None:
    """Module startup hook - register RBAC permissions."""
    from app.modules.file_distribution.permissions import (
        register_file_distribution_permissions,
    )

    register_file_distribution_permissions()
