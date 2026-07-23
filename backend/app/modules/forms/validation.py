# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure validation engine for forms and checklists.

This module is deliberately dependency-free - stdlib only, no ORM, no FastAPI,
no app imports - so it can be unit tested on a bare interpreter without the
application graph or a database, and reused unchanged on both the create path
(template integrity) and the complete path (submission completeness).

Two jobs, both first-class in the workflow (nothing is stored or completed
without passing the relevant check):

* :func:`validate_template_fields` - a template is only coherent if every field
  is well formed: a choice field carries options, keys are unique, a rating has
  a sane scale, and there is at least one thing to actually fill in.
* :func:`validate_submission_answers` - a submission may only be *completed* when
  every required field is answered and every provided answer is consistent with
  its field (a choice value that exists, a number that parses, a photo or
  signature actually present where the field demands one).

Both return a list of :class:`FieldIssue` (empty == valid). Callers turn a
non-empty list into an HTTP 422 with the issues attached; the pure layer never
raises for *data* problems so it stays trivially testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

# Branching logic lives in the sibling ``conditional`` module. Prefer the normal
# package import; fall back to loading it from disk when this module is itself
# loaded by file path in the isolated unit tests (no package context), so the
# pure layer stays testable on a bare interpreter - just like the rest of it.
try:
    from .conditional import collect_rule_issues, evaluate_visibility, sanitize_expr
except ImportError:  # pragma: no cover - exercised only under path-based loading
    import importlib.util as _importlib_util
    import sys as _sys
    from pathlib import Path as _Path

    if "forms_conditional" in _sys.modules:
        _conditional = _sys.modules["forms_conditional"]
    else:
        _conditional_path = _Path(__file__).resolve().parent / "conditional.py"
        _spec = _importlib_util.spec_from_file_location("forms_conditional", _conditional_path)
        assert _spec and _spec.loader
        _conditional = _importlib_util.module_from_spec(_spec)
        _sys.modules["forms_conditional"] = _conditional
        _spec.loader.exec_module(_conditional)
    collect_rule_issues = _conditional.collect_rule_issues
    evaluate_visibility = _conditional.evaluate_visibility
    sanitize_expr = _conditional.sanitize_expr

# ── Field vocabulary ─────────────────────────────────────────────────────────

# Every field type a template may compose. Ordered as they appear in the
# builder palette. Keep in lock-step with the frontend FIELD_TYPES list.
FIELD_TYPES: tuple[str, ...] = (
    "section",  # a heading / divider - carries no answer
    "short_text",
    "long_text",
    "number",  # numeric, optional unit
    "single_choice",  # pick one of options
    "multi_choice",  # pick any of options
    "checkbox",  # a single boolean acknowledgement
    "pass_fail_na",  # pass / fail / n/a - the checklist workhorse
    "rating",  # 1..max_rating
    "photo",  # photo evidence (one or more references)
    "signature",  # a captured signature (name + optional image data)
    "date",
)

# Types that require a non-empty ``options`` list to mean anything.
CHOICE_TYPES: frozenset[str] = frozenset({"single_choice", "multi_choice"})

# Types that carry no answer - they structure the form but are never filled in.
LAYOUT_TYPES: frozenset[str] = frozenset({"section"})

# The pass/fail/NA values a checklist item may take (lower-cased on compare).
PASS_FAIL_VALUES: frozenset[str] = frozenset({"pass", "fail", "na"})

# Template categories. ``custom`` is the catch-all for anything user-defined.
CATEGORIES: tuple[str, ...] = (
    "safety",
    "quality",
    "handover",
    "inspection",
    "commissioning",
    "custom",
)

# Guard rails so a hand-crafted rating scale stays legible.
RATING_MIN_SCALE = 2
RATING_MAX_SCALE = 10
DEFAULT_RATING_SCALE = 5

# Ceiling on field count per template - a builder that lets a user add 5000
# fields is a footgun, not a feature.
MAX_FIELDS_PER_TEMPLATE = 300


# ── Issue model ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FieldIssue:
    """One problem found with a field definition or an answer.

    ``field_index`` locates the field in the ordered list; ``field_key`` is its
    stable key when one exists. ``code`` is a stable machine token (for the UI
    to branch on / translate), ``message`` a plain-English fallback.
    """

    field_index: int
    field_key: str | None
    code: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        """Serialise for an HTTP error payload."""
        return {
            "field_index": self.field_index,
            "field_key": self.field_key,
            "code": self.code,
            "message": self.message,
        }


# ── Helpers ──────────────────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Reduce a label to a stable lower-snake key fragment.

    Empty / punctuation-only text yields ``""`` so the caller can fall back to
    a positional key (``field_1``) instead of emitting an empty key.
    """
    slug = _SLUG_RE.sub("_", str(text or "").strip().lower()).strip("_")
    return slug[:60]


def normalize_fields(raw_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a cleaned copy of ``raw_fields`` with keys and defaults filled.

    Does not validate (that is :func:`validate_template_fields`); it only makes
    the list canonical so persistence and validation see the same shape:

    * a missing / blank ``key`` is derived from the label (``slugify``), then
      de-duplicated with a numeric suffix so keys stay unique;
    * ``required`` is coerced to bool and forced ``False`` for layout fields;
    * ``options`` is coerced to a list of trimmed strings;
    * ``max_rating`` defaults to :data:`DEFAULT_RATING_SCALE` for rating fields.

    The input is never mutated.
    """
    cleaned: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for idx, raw in enumerate(raw_fields):
        src = dict(raw) if isinstance(raw, dict) else {}
        ftype = str(src.get("type", "")).strip()
        label = str(src.get("label", "")).strip()

        # Derive a stable, unique key.
        key = str(src.get("key", "")).strip()
        if not key:
            key = slugify(label) or f"field_{idx + 1}"
        base_key = key
        suffix = 2
        while key in seen_keys:
            key = f"{base_key}_{suffix}"
            suffix += 1
        seen_keys.add(key)

        field: dict[str, Any] = {
            "key": key,
            "type": ftype,
            "label": label,
            "help_text": str(src.get("help_text", "") or "").strip() or None,
        }

        is_layout = ftype in LAYOUT_TYPES
        field["required"] = bool(src.get("required", False)) and not is_layout

        if ftype in CHOICE_TYPES:
            field["options"] = _clean_options(src.get("options"))
        if ftype == "number":
            unit = str(src.get("unit", "") or "").strip()
            field["unit"] = unit or None
        if ftype == "rating":
            field["max_rating"] = _coerce_rating_scale(src.get("max_rating"))

        # Carry optional branching rules through, cleaned to a compact JSON-safe
        # shape. Absent / empty rules are simply omitted (the field is
        # unconditionally shown / uses its static ``required`` flag).
        visible_if = sanitize_expr(src.get("visible_if"))
        if visible_if is not None:
            field["visible_if"] = visible_if
        required_if = sanitize_expr(src.get("required_if"))
        if required_if is not None:
            field["required_if"] = required_if

        cleaned.append(field)
    return cleaned


def _clean_options(raw: Any) -> list[str]:
    """Coerce an options value to a list of trimmed, de-duplicated strings."""
    if not isinstance(raw, (list, tuple)):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        text = str(item).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _coerce_rating_scale(raw: Any) -> int:
    """Coerce a rating scale to an int, defaulting when absent / unparseable."""
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_RATING_SCALE
    return value


# ── Template integrity ───────────────────────────────────────────────────────


def validate_template_fields(fields: list[dict[str, Any]]) -> list[FieldIssue]:
    """Validate a template's field definitions. Empty list == valid.

    Assumes ``fields`` has been through :func:`normalize_fields` (keys present,
    options coerced) but does not rely on it for safety - it re-checks the
    invariants that matter:

    * at least one and at most :data:`MAX_FIELDS_PER_TEMPLATE` fields;
    * at least one non-layout field (a template of only headers cannot be filled);
    * each field: known type, non-empty label, non-empty unique key;
    * a choice field carries at least two distinct options;
    * a rating field's scale is within [:data:`RATING_MIN_SCALE`,
      :data:`RATING_MAX_SCALE`];
    * every ``visible_if`` / ``required_if`` branching rule is well formed - a
      whitelisted operator, a field that exists, no self reference (see
      :func:`conditional.collect_rule_issues`).
    """
    issues: list[FieldIssue] = []

    if not fields:
        issues.append(FieldIssue(-1, None, "no_fields", "A template needs at least one field."))
        return issues
    if len(fields) > MAX_FIELDS_PER_TEMPLATE:
        issues.append(
            FieldIssue(
                -1,
                None,
                "too_many_fields",
                f"A template may have at most {MAX_FIELDS_PER_TEMPLATE} fields.",
            )
        )

    seen_keys: set[str] = set()
    fillable = 0
    for idx, field in enumerate(fields):
        ftype = str(field.get("type", "")).strip()
        label = str(field.get("label", "")).strip()
        key = str(field.get("key", "")).strip()

        if ftype not in FIELD_TYPES:
            issues.append(FieldIssue(idx, key or None, "unknown_type", f"Unknown field type '{ftype or '(blank)'}'."))
        if not label:
            issues.append(FieldIssue(idx, key or None, "missing_label", "Every field needs a label."))
        if not key:
            issues.append(FieldIssue(idx, None, "missing_key", "Every field needs a key."))
        elif key in seen_keys:
            issues.append(FieldIssue(idx, key, "duplicate_key", f"Duplicate field key '{key}'."))
        else:
            seen_keys.add(key)

        if ftype not in LAYOUT_TYPES:
            fillable += 1

        if ftype in CHOICE_TYPES:
            options = field.get("options")
            distinct = _clean_options(options)
            if len(distinct) < 2:
                issues.append(
                    FieldIssue(
                        idx,
                        key or None,
                        "choice_needs_options",
                        "A choice field needs at least two distinct options.",
                    )
                )

        if ftype == "rating":
            scale = _coerce_rating_scale(field.get("max_rating"))
            if not (RATING_MIN_SCALE <= scale <= RATING_MAX_SCALE):
                issues.append(
                    FieldIssue(
                        idx,
                        key or None,
                        "rating_scale",
                        f"A rating scale must be between {RATING_MIN_SCALE} and {RATING_MAX_SCALE}.",
                    )
                )

    if fillable == 0:
        issues.append(
            FieldIssue(
                -1,
                None,
                "no_fillable_field",
                "A template needs at least one field to fill in, not only section headers.",
            )
        )

    # Branching rules: a bad operator / dangling reference is a template bug,
    # rejected here so it never reaches storage or a submission snapshot.
    issues.extend(FieldIssue(ri.field_index, ri.field_key, ri.code, ri.message) for ri in collect_rule_issues(fields))

    return issues


# ── Submission completeness / consistency ────────────────────────────────────


@dataclass
class SubmissionCheck:
    """Outcome of validating a submission's answers against its fields."""

    issues: list[FieldIssue] = dataclass_field(default_factory=list)
    answered_required: int = 0
    total_required: int = 0

    @property
    def is_complete(self) -> bool:
        """True when there are no issues (every required field answered, all
        provided answers well formed)."""
        return not self.issues


def validate_submission_answers(
    fields: list[dict[str, Any]],
    answers: dict[str, Any],
) -> SubmissionCheck:
    """Validate ``answers`` against the (snapshotted) template ``fields``.

    Two concerns, both blocking a Complete:

    * completeness - every ``required`` non-layout field has a non-empty answer
      (a required checkbox must be ticked; a required photo / signature field
      must actually carry a photo / signature);
    * consistency - any *provided* answer must be well formed for its type: a
      choice value must be one of the options, a number must parse, a rating
      must sit inside the scale, a pass/fail/na must be one of those three.

    Branching logic is honoured first (see :func:`conditional.evaluate_visibility`):
    a field hidden by a ``visible_if`` rule is skipped entirely - neither required
    nor consistency-checked, so a value left over from an untaken branch never
    blocks completion - and a field a ``required_if`` rule switches on is enforced
    exactly like a statically required one.

    Absent answers to optional (or hidden) fields are fine and never reported.
    """
    check = SubmissionCheck()
    answers = answers or {}
    visibility = evaluate_visibility(fields, answers)

    for idx, field in enumerate(fields):
        ftype = str(field.get("type", "")).strip()
        if ftype in LAYOUT_TYPES:
            continue

        key = str(field.get("key", "")).strip()
        state = visibility.get(key)
        if state is not None and not state["visible"]:
            # Hidden by a branching rule: not required, value ignored.
            continue
        required = state["required"] if state is not None else bool(field.get("required", False))
        value = answers.get(key)
        empty = _is_empty_answer(ftype, value)

        if required:
            check.total_required += 1

        if empty:
            if required:
                check.issues.append(
                    FieldIssue(
                        idx,
                        key or None,
                        "required_missing",
                        f"'{field.get('label') or key}' is required.",
                    )
                )
            continue

        if required:
            check.answered_required += 1

        value_issue = _answer_value_issue(idx, field, value)
        if value_issue is not None:
            check.issues.append(value_issue)

    return check


def _is_empty_answer(ftype: str, value: Any) -> bool:
    """Whether ``value`` counts as "not answered" for a field of ``ftype``.

    A ``checkbox`` is special: an *unticked* box (``False``) is treated as
    empty, so a required acknowledgement checkbox genuinely forces a tick
    rather than accepting the default.
    """
    if value is None:
        return True
    if ftype == "checkbox":
        return value is not True
    if ftype in ("short_text", "long_text", "pass_fail_na", "date", "single_choice"):
        return str(value).strip() == ""
    if ftype == "multi_choice":
        return not (isinstance(value, (list, tuple)) and len([v for v in value if str(v).strip()]) > 0)
    if ftype == "photo":
        # Accept a list of references or a single non-empty reference/marker.
        if isinstance(value, (list, tuple)):
            return len([v for v in value if str(v).strip()]) == 0
        return str(value).strip() == ""
    if ftype == "signature":
        return _signature_is_empty(value)
    if ftype in ("number", "rating"):
        return str(value).strip() == "" if isinstance(value, str) else value is None
    return str(value).strip() == "" if isinstance(value, str) else False


def _signature_is_empty(value: Any) -> bool:
    """A signature is present when it has a signer name or captured image data."""
    if isinstance(value, dict):
        name = str(value.get("name", "") or "").strip()
        data = str(value.get("data", "") or "").strip()
        return not (name or data)
    return str(value or "").strip() == ""


def _answer_value_issue(idx: int, field: dict[str, Any], value: Any) -> FieldIssue | None:
    """Consistency check for a *provided* answer. None == fine.

    Only reached for non-empty answers, so it never doubles up with the
    required-missing check.
    """
    ftype = str(field.get("type", "")).strip()
    key = str(field.get("key", "")).strip() or None

    if ftype == "single_choice":
        options = _clean_options(field.get("options"))
        if str(value).strip() not in options:
            return FieldIssue(idx, key, "invalid_choice", "Answer is not one of the allowed options.")
        return None

    if ftype == "multi_choice":
        options = set(_clean_options(field.get("options")))
        picked = value if isinstance(value, (list, tuple)) else [value]
        for item in picked:
            if str(item).strip() and str(item).strip() not in options:
                return FieldIssue(idx, key, "invalid_choice", f"'{item}' is not one of the allowed options.")
        return None

    if ftype == "pass_fail_na":
        if str(value).strip().lower() not in PASS_FAIL_VALUES:
            return FieldIssue(idx, key, "invalid_pass_fail", "Answer must be pass, fail or n/a.")
        return None

    if ftype == "number":
        if _to_float(value) is None:
            return FieldIssue(idx, key, "not_a_number", "Answer must be a number.")
        return None

    if ftype == "rating":
        scale = _coerce_rating_scale(field.get("max_rating"))
        rating = _to_float(value)
        if rating is None or not (1 <= rating <= scale) or float(rating).is_integer() is False:
            return FieldIssue(idx, key, "invalid_rating", f"Rating must be a whole number from 1 to {scale}.")
        return None

    return None


def _to_float(value: Any) -> float | None:
    """Parse a numeric answer to float, tolerating a comma decimal. None on fail."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "").strip().replace(",", ".")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None
