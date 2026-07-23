# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Clash domain events.

The clash service publishes these onto the global event bus so other
modules can react without a direct import. Notifications subscribes to
``clash.high_severity.detected`` to alert the relevant users when a
high- or critical-severity interference is found or confirmed.

Severities that count as "high" for the purpose of this event are
defined in :data:`HIGH_SEVERITIES`. The payload always carries enough
context (``project_id``, ``run_id``, ``result_id``, ``severity``,
``trigger`` and the two element names) for a subscriber to build a
notification without re-querying the clash tables.
"""

from __future__ import annotations

# Event name constants -------------------------------------------------------

CLASH_HIGH_SEVERITY_DETECTED = "clash.high_severity.detected"


# Severity levels that warrant a cross-module alert. Mirrors the
# ``CLASH_SEVERITIES`` enum ("critical", "high", "medium", "low") but
# keeps only the two top bands.
HIGH_SEVERITIES: frozenset[str] = frozenset({"critical", "high"})


# Trigger discriminator carried in the payload so subscribers can phrase
# the notification differently ("detected" vs "confirmed by review").
TRIGGER_CREATED = "created"
TRIGGER_CONFIRMED = "confirmed"


ALL_EVENTS: tuple[str, ...] = (CLASH_HIGH_SEVERITY_DETECTED,)
