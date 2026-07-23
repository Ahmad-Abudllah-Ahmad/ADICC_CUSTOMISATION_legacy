# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Saved-views event names.

Thin event identifiers other modules can subscribe to (the dashboards /
automation layers later consume these). The event bus publish/subscribe lives in
``app.core.events``; this module only declares the canonical names so emitters
and subscribers agree on the string.
"""

from __future__ import annotations

# Emitted when a user persists a new saved view.
EVENT_SAVED_VIEW_CREATED = "saved_view.created"
# Emitted after a saved view (or ad-hoc spec) is run.
EVENT_SAVED_VIEW_RUN = "saved_view.run"
