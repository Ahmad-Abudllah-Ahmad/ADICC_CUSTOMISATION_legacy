# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Final-account (close-out) readiness checklist - pure, dependency-free.

Evaluates the close-out conditions of a construction contract from data the
contracts module already stores (progress claims, extension-of-time claims,
financial securities, retention figures and the final account row). Nothing
here imports SQLAlchemy or FastAPI, so the whole checklist unit-tests without a
database: the service loads the rows, flattens them into a plain
:class:`ClosureFacts` value object and calls
:func:`evaluate_final_account_readiness`.

Each check reports a status (``pass`` / ``fail`` / ``not_applicable``) with a
short reason and the values it was based on. The overall result is ``ready``
(every applicable check passed and at least one applies) plus a completion
percentage - checks passed over applicable checks, guarded against a zero
divisor.

Money is handled with :class:`~decimal.Decimal` throughout and serialised as
strings in the ``based_on`` map so no float ever reaches the response.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# Stable check identifiers (safe for UI wiring / i18n keys).
CHECK_PROGRESS_CLAIMS_SETTLED = "progress_claims_settled"
CHECK_EOT_CLAIMS_DECIDED = "eot_claims_decided"
CHECK_SECURITIES_RELEASED = "securities_released"
CHECK_RETENTION_RELEASED = "retention_released"
CHECK_FINAL_CERTIFICATE_ISSUED = "final_certificate_issued"
CHECK_FINAL_VALUE_RECONCILED = "final_value_reconciled"

# Per-check statuses.
STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_NA = "not_applicable"

_DEC_ZERO = Decimal("0")
_DEC_HUNDRED = Decimal("100")
_DEC_CENTS = Decimal("0.01")

__all__ = [
    "CHECK_EOT_CLAIMS_DECIDED",
    "CHECK_FINAL_CERTIFICATE_ISSUED",
    "CHECK_FINAL_VALUE_RECONCILED",
    "CHECK_PROGRESS_CLAIMS_SETTLED",
    "CHECK_RETENTION_RELEASED",
    "CHECK_SECURITIES_RELEASED",
    "STATUS_FAIL",
    "STATUS_NA",
    "STATUS_PASS",
    "ChecklistItem",
    "ClosureFacts",
    "FinalAccountChecklist",
    "completion_percent",
    "evaluate_final_account_readiness",
]


def _dec(value: object) -> Decimal:
    """Coerce any money-like value into a Decimal, defaulting to zero."""
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value if value is not None else 0))
    except (ArithmeticError, ValueError, TypeError):
        return _DEC_ZERO


@dataclass(frozen=True)
class ClosureFacts:
    """DB-free snapshot of a contract's close-out state.

    Every field is derived by the service from rows the contracts module
    already persists; the checklist evaluator never touches the database.
    """

    # Reconciliation.
    contract_total_value: Decimal = _DEC_ZERO
    # Progress / payment claims (open = not yet paid and not rejected).
    open_progress_claim_count: int = 0
    total_progress_claim_count: int = 0
    # Extension-of-time claims (pending = not yet decided or withdrawn).
    pending_eot_count: int = 0
    total_eot_count: int = 0
    # Financial securities (outstanding = still required / received / active).
    outstanding_security_count: int = 0
    total_security_count: int = 0
    # Retention.
    retention_held: Decimal = _DEC_ZERO
    retention_released: Decimal = _DEC_ZERO
    # Final account / final certificate.
    final_account_present: bool = False
    final_account_agreed: bool = False  # status in {agreed, closed}
    final_account_signed_off: bool = False  # sign-off date recorded
    final_account_value: Decimal = _DEC_ZERO


@dataclass(frozen=True)
class ChecklistItem:
    """One close-out condition with its outcome and supporting values."""

    key: str
    status: str
    reason: str
    based_on: dict[str, str]


@dataclass(frozen=True)
class FinalAccountChecklist:
    """Full checklist result: the items plus the overall readiness roll-up."""

    items: list[ChecklistItem]
    ready: bool
    completion_percent: Decimal
    passed_count: int
    applicable_count: int
    total_count: int


def completion_percent(passed: int, applicable: int) -> Decimal:
    """Percentage of applicable checks that passed, guarded against zero.

    Returns a Decimal in the range 0..100 quantised to two places. When no
    check applies (``applicable`` <= 0) the guarded result is ``Decimal('0')``
    instead of a division error.
    """
    if applicable <= 0:
        return _DEC_ZERO
    return (Decimal(passed) / Decimal(applicable) * _DEC_HUNDRED).quantize(_DEC_CENTS)


def _check_progress_claims(facts: ClosureFacts) -> ChecklistItem:
    total = max(int(facts.total_progress_claim_count), 0)
    open_count = max(int(facts.open_progress_claim_count), 0)
    based_on = {"open_claim_count": str(open_count), "total_claim_count": str(total)}
    if open_count == 0:
        reason = (
            "All progress claims are settled (paid or rejected)."
            if total
            else "No progress claims were raised on this contract."
        )
        return ChecklistItem(CHECK_PROGRESS_CLAIMS_SETTLED, STATUS_PASS, reason, based_on)
    reason = f"{open_count} of {total} progress claims are still open."
    return ChecklistItem(CHECK_PROGRESS_CLAIMS_SETTLED, STATUS_FAIL, reason, based_on)


def _check_eot_claims(facts: ClosureFacts) -> ChecklistItem:
    total = max(int(facts.total_eot_count), 0)
    pending = max(int(facts.pending_eot_count), 0)
    based_on = {"pending_eot_count": str(pending), "total_eot_count": str(total)}
    if total == 0:
        reason = "No extension-of-time claims were raised on this contract."
        return ChecklistItem(CHECK_EOT_CLAIMS_DECIDED, STATUS_NA, reason, based_on)
    if pending == 0:
        reason = f"All {total} extension-of-time claims have been decided."
        return ChecklistItem(CHECK_EOT_CLAIMS_DECIDED, STATUS_PASS, reason, based_on)
    reason = f"{pending} of {total} extension-of-time claims are still awaiting a decision."
    return ChecklistItem(CHECK_EOT_CLAIMS_DECIDED, STATUS_FAIL, reason, based_on)


def _check_securities(facts: ClosureFacts) -> ChecklistItem:
    total = max(int(facts.total_security_count), 0)
    outstanding = max(int(facts.outstanding_security_count), 0)
    based_on = {
        "outstanding_security_count": str(outstanding),
        "total_security_count": str(total),
    }
    if total == 0:
        reason = "No bonds, guarantees or insurance are registered on this contract."
        return ChecklistItem(CHECK_SECURITIES_RELEASED, STATUS_NA, reason, based_on)
    if outstanding == 0:
        reason = f"All {total} financial securities have been released or expired."
        return ChecklistItem(CHECK_SECURITIES_RELEASED, STATUS_PASS, reason, based_on)
    reason = f"{outstanding} of {total} financial securities are still outstanding."
    return ChecklistItem(CHECK_SECURITIES_RELEASED, STATUS_FAIL, reason, based_on)


def _check_retention(facts: ClosureFacts) -> ChecklistItem:
    held = _dec(facts.retention_held)
    released = _dec(facts.retention_released)
    outstanding = held - released
    shown_outstanding = outstanding if outstanding > _DEC_ZERO else _DEC_ZERO
    based_on = {
        "retention_held": str(held),
        "retention_released": str(released),
        "retention_outstanding": str(shown_outstanding),
    }
    if held <= _DEC_ZERO:
        reason = "No retention was withheld on this contract."
        return ChecklistItem(CHECK_RETENTION_RELEASED, STATUS_NA, reason, based_on)
    if outstanding <= _DEC_ZERO:
        reason = "Retention has been fully released."
        return ChecklistItem(CHECK_RETENTION_RELEASED, STATUS_PASS, reason, based_on)
    reason = f"{shown_outstanding} of {held} retention is still held."
    return ChecklistItem(CHECK_RETENTION_RELEASED, STATUS_FAIL, reason, based_on)


def _check_final_certificate(facts: ClosureFacts) -> ChecklistItem:
    based_on = {
        "final_account_present": str(bool(facts.final_account_present)).lower(),
        "final_account_agreed": str(bool(facts.final_account_agreed)).lower(),
        "final_account_signed_off": str(bool(facts.final_account_signed_off)).lower(),
    }
    if facts.final_account_present and facts.final_account_agreed and facts.final_account_signed_off:
        reason = "The final account has been agreed and signed off."
        return ChecklistItem(CHECK_FINAL_CERTIFICATE_ISSUED, STATUS_PASS, reason, based_on)
    if not facts.final_account_present:
        reason = "No final account has been prepared yet."
    elif not facts.final_account_agreed:
        reason = "The final account is not yet agreed."
    else:
        reason = "The final account has not been signed off."
    return ChecklistItem(CHECK_FINAL_CERTIFICATE_ISSUED, STATUS_FAIL, reason, based_on)


def _check_final_value(facts: ClosureFacts) -> ChecklistItem:
    contract_value = _dec(facts.contract_total_value)
    if not facts.final_account_present:
        based_on = {
            "final_account_value": "",
            "contract_total_value": str(contract_value),
            "difference": "",
        }
        reason = "No final account value has been agreed to reconcile yet."
        return ChecklistItem(CHECK_FINAL_VALUE_RECONCILED, STATUS_NA, reason, based_on)
    agreed = _dec(facts.final_account_value)
    difference = agreed - contract_value
    based_on = {
        "final_account_value": str(agreed),
        "contract_total_value": str(contract_value),
        "difference": str(difference),
    }
    if difference == _DEC_ZERO:
        reason = "The agreed final value reconciles with the contract sum to date."
        return ChecklistItem(CHECK_FINAL_VALUE_RECONCILED, STATUS_PASS, reason, based_on)
    reason = "The agreed final value does not match the contract sum to date."
    return ChecklistItem(CHECK_FINAL_VALUE_RECONCILED, STATUS_FAIL, reason, based_on)


# Order defines the display order of the checklist.
_CHECK_BUILDERS = (
    _check_progress_claims,
    _check_eot_claims,
    _check_securities,
    _check_retention,
    _check_final_certificate,
    _check_final_value,
)


def evaluate_final_account_readiness(facts: ClosureFacts) -> FinalAccountChecklist:
    """Evaluate every close-out condition and roll up an overall readiness.

    ``ready`` is true only when at least one check applies and none failed.
    ``completion_percent`` counts passed over applicable checks (not-applicable
    checks are excluded), guarded against a zero divisor.
    """
    items = [build(facts) for build in _CHECK_BUILDERS]
    passed = sum(1 for item in items if item.status == STATUS_PASS)
    failed = sum(1 for item in items if item.status == STATUS_FAIL)
    applicable = passed + failed
    ready = applicable > 0 and failed == 0
    return FinalAccountChecklist(
        items=items,
        ready=ready,
        completion_percent=completion_percent(passed, applicable),
        passed_count=passed,
        applicable_count=applicable,
        total_count=len(items),
    )
