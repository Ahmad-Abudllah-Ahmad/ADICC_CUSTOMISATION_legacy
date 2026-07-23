# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
"""Status-banding thresholds for the controls spine.

Region-neutral defaults. A threshold entry carries an ``amber`` and ``red``
boundary plus a ``direction`` telling the bander whether higher or lower is
worse (CPI lower is worse, TRIR higher is worse). Partner packs override these
declaratively without touching core code.

``direction``:
    * ``lower_is_worse`` - value below ``amber`` is amber, below ``red`` is red.
    * ``higher_is_worse`` - value above ``amber`` is amber, above ``red`` is red.

A KPI with no threshold entry always bands ``green`` (no opinion).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

# direction constants
LOWER_IS_WORSE = "lower_is_worse"
HIGHER_IS_WORSE = "higher_is_worse"

# Region-neutral default thresholds keyed by KPI code.
DEFAULT_THRESHOLDS: dict[str, dict[str, Any]] = {
    # Cost / schedule performance indices - below 1.0 means behind.
    "cpi": {"amber": "0.95", "red": "0.90", "direction": LOWER_IS_WORSE},
    "spi": {"amber": "0.95", "red": "0.90", "direction": LOWER_IS_WORSE},
    # Variances: negative is overrun / behind.
    "cv": {"amber": "0", "red": "-1", "direction": LOWER_IS_WORSE},
    "sv": {"amber": "0", "red": "-1", "direction": LOWER_IS_WORSE},
    # VAC negative = projected over budget at completion.
    "vac": {"amber": "0", "red": "-1", "direction": LOWER_IS_WORSE},
    # Quality.
    "first_pass_yield": {"amber": "95", "red": "85", "direction": LOWER_IS_WORSE},
    "ncr_open_count": {"amber": "3", "red": "8", "direction": HIGHER_IS_WORSE},
    "rfi_close_avg_days": {"amber": "7", "red": "14", "direction": HIGHER_IS_WORSE},
    # Safety.
    "safety_trir": {"amber": "1.0", "red": "3.0", "direction": HIGHER_IS_WORSE},
    "incident_count": {"amber": "1", "red": "5", "direction": HIGHER_IS_WORSE},
    # Risk.
    "risk_high_unmitigated_count": {"amber": "1", "red": "3", "direction": HIGHER_IS_WORSE},
    # Changes.
    "change_order_ratio": {"amber": "5", "red": "10", "direction": HIGHER_IS_WORSE},
    # Schedule slippage in days.
    "milestone_slippage_days": {"amber": "7", "red": "30", "direction": HIGHER_IS_WORSE},
}


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def band_status(
    code: str,
    value: Any,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> str:
    """Return ``"green" | "amber" | "red"`` for a KPI value.

    ``overrides`` (e.g. a saved view's ``thresholds_json``) take precedence
    over :data:`DEFAULT_THRESHOLDS`. A KPI with no threshold, or an
    unparseable value, bands ``green``.
    """
    rule = None
    if overrides and code in overrides:
        rule = overrides[code]
    elif code in DEFAULT_THRESHOLDS:
        rule = DEFAULT_THRESHOLDS[code]
    if not rule:
        return "green"

    val = _to_decimal(value)
    amber = _to_decimal(rule.get("amber"))
    red = _to_decimal(rule.get("red"))
    if val is None or amber is None or red is None:
        return "green"

    direction = rule.get("direction", LOWER_IS_WORSE)
    if direction == HIGHER_IS_WORSE:
        if val >= red:
            return "red"
        if val >= amber:
            return "amber"
        return "green"
    # lower_is_worse (default)
    if val <= red:
        return "red"
    if val <= amber:
        return "amber"
    return "green"
