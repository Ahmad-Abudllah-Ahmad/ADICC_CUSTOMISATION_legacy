# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure heuristic detector for construction delay signals in free text.

Scans an unstructured note - an imported email body, a site-diary entry, or a
request-for-information - for language that commonly accompanies a delay event,
and proposes a small starter set of schedule activities (a fragnet) to seed a
forensic-delay workflow. The aim is to surface a likely cause and a sensible
first response for a human to confirm, not to adjudicate an entitlement.

Detection is plain keyword and regular-expression matching against a fixed map
of categories (adverse weather, blocked site access, late information, design
change, variation, resource shortage, statutory approval, and unforeseen ground
conditions). Each category carries trigger phrases matched on word boundaries,
case-insensitively, and a short list of suggested follow-up activities.
Confidence is a bounded heuristic from the number of distinct phrases found; it
is a triage hint, not a probability.

Stdlib only (``re`` and ``dataclasses``), so it imports and unit-tests on the
local runner. :func:`detect_from_email` reads a :class:`ParsedEmail` from the
sibling parser, keeping the whole module dependency-free.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "CATEGORY_ACTIVITIES",
    "CATEGORY_PHRASES",
    "DelaySignal",
    "detect_delays",
    "detect_from_email",
]


@dataclass(frozen=True)
class DelaySignal:
    """One detected delay category with its evidence and a suggested fragnet.

    ``confidence`` is a bounded heuristic in the range 0.0 to 1.0 derived from
    how many distinct trigger phrases were found. ``matched_phrases`` lists the
    canonical trigger phrases that fired (de-duplicated). ``suggested_activities``
    is the category's fixed starter fragnet.
    """

    category: str
    confidence: float
    matched_phrases: list[str]
    suggested_activities: list[str]


# Canonical category tokens. Stable strings so callers and stored records can
# key off them without depending on display wording.
CATEGORY_WEATHER = "weather"
CATEGORY_SITE_ACCESS = "site_access"
CATEGORY_LATE_INFORMATION = "late_information"
CATEGORY_DESIGN_CHANGE = "design_change"
CATEGORY_VARIATION = "variation"
CATEGORY_RESOURCE_SHORTAGE = "resource_shortage"
CATEGORY_STATUTORY_APPROVAL = "statutory_approval"
CATEGORY_UNFORESEEN_GROUND = "unforeseen_ground"


# Trigger phrases per category. Matched case-insensitively on word boundaries,
# so multi-word phrases match as a unit and a short word does not match inside a
# longer one. Kept human-readable; these double as the canonical labels that
# appear in ``matched_phrases``.
CATEGORY_PHRASES: dict[str, list[str]] = {
    CATEGORY_WEATHER: [
        "rain",
        "heavy rain",
        "storm",
        "flooding",
        "flood",
        "frost",
        "high winds",
        "gale",
        "snow",
        "ice",
        "adverse weather",
        "inclement weather",
        "exceptionally adverse weather",
    ],
    CATEGORY_SITE_ACCESS: [
        "no access",
        "denied access",
        "access denied",
        "site closed",
        "site shutdown",
        "road closure",
        "blocked access",
        "cannot access",
        "unable to access",
        "possession of site",
        "late access",
        "access restricted",
    ],
    CATEGORY_LATE_INFORMATION: [
        "awaiting information",
        "missing drawings",
        "missing information",
        "rfi overdue",
        "rfi outstanding",
        "late response",
        "no response",
        "awaiting response",
        "information not received",
        "awaiting instruction",
        "pending approval of drawings",
        "outstanding information",
    ],
    CATEGORY_DESIGN_CHANGE: [
        "design change",
        "revised drawings",
        "design revision",
        "redesign",
        "amended design",
        "drawing revision",
        "specification change",
        "changed specification",
        "revised specification",
    ],
    CATEGORY_VARIATION: [
        "variation",
        "change order",
        "variation order",
        "additional works",
        "additional work",
        "extra works",
        "extra work",
        "scope change",
        "instructed change",
        "client instruction",
    ],
    CATEGORY_RESOURCE_SHORTAGE: [
        "labour shortage",
        "labor shortage",
        "shortage of labour",
        "shortage of labor",
        "material shortage",
        "shortage of materials",
        "no materials",
        "awaiting materials",
        "plant breakdown",
        "equipment breakdown",
        "insufficient resources",
        "supply delay",
        "delivery delay",
        "late delivery",
    ],
    CATEGORY_STATUTORY_APPROVAL: [
        "permit",
        "permit pending",
        "awaiting permit",
        "building permit",
        "planning permission",
        "planning approval",
        "regulatory approval",
        "statutory approval",
        "consent pending",
        "awaiting consent",
        "inspection failed",
        "authority approval",
    ],
    CATEGORY_UNFORESEEN_GROUND: [
        "rock",
        "hard rock",
        "contamination",
        "contaminated ground",
        "groundwater",
        "ground water",
        "obstruction",
        "buried obstruction",
        "unforeseen ground",
        "unexpected ground conditions",
        "unstable ground",
        "running sand",
    ],
}


# Fixed starter fragnet per category: a few schedule activities a planner would
# typically open in response. Confirmed and refined by a human downstream.
CATEGORY_ACTIVITIES: dict[str, list[str]] = {
    CATEGORY_WEATHER: [
        "Record adverse weather days",
        "Assess critical-path impact",
        "Submit extension-of-time notice",
    ],
    CATEGORY_SITE_ACCESS: [
        "Log access restriction and duration",
        "Notify employer of denied access",
        "Reschedule affected activities",
    ],
    CATEGORY_LATE_INFORMATION: [
        "Log outstanding information request",
        "Issue reminder for missing information",
        "Assess impact of late information on the programme",
    ],
    CATEGORY_DESIGN_CHANGE: [
        "Capture revised design issue",
        "Reprice and re-sequence affected work",
        "Update the programme for the design change",
    ],
    CATEGORY_VARIATION: [
        "Raise variation record",
        "Estimate cost and time effect",
        "Submit notice of delay and disruption",
    ],
    CATEGORY_RESOURCE_SHORTAGE: [
        "Log resource or supply shortage",
        "Re-plan affected activities",
        "Expedite procurement or redeployment",
    ],
    CATEGORY_STATUTORY_APPROVAL: [
        "Track outstanding approval or permit",
        "Escalate with the relevant authority",
        "Hold dependent activities pending approval",
    ],
    CATEGORY_UNFORESEEN_GROUND: [
        "Record unforeseen ground condition",
        "Instruct survey or investigation",
        "Submit notice for changed conditions",
    ],
}


def _compile_patterns() -> dict[str, list[tuple[str, re.Pattern[str]]]]:
    """Pre-compile a word-boundary, case-insensitive pattern per phrase.

    Returns, per category, a list of (canonical phrase, compiled pattern). The
    pattern tolerates any run of whitespace between words of a multi-word
    phrase so a line break or double space inside the source still matches.
    """
    compiled: dict[str, list[tuple[str, re.Pattern[str]]]] = {}
    for category, phrases in CATEGORY_PHRASES.items():
        entries: list[tuple[str, re.Pattern[str]]] = []
        for phrase in phrases:
            tokens = phrase.split()
            escaped = r"\s+".join(re.escape(tok) for tok in tokens)
            pattern = re.compile(rf"\b{escaped}\b", re.IGNORECASE)
            entries.append((phrase, pattern))
        compiled[category] = entries
    return compiled


# Built once at import; the maps above are module-level constants.
_PATTERNS = _compile_patterns()


def detect_delays(text: str) -> list[DelaySignal]:
    """Detect likely delay categories in *text*.

    For every category with at least one trigger phrase present, returns a
    :class:`DelaySignal` whose ``confidence`` is ``min(1.0, distinct_matches /
    3.0)`` - one phrase is a weak hint, three or more saturate the score. Empty
    or non-matching input returns an empty list. Results are sorted by
    confidence descending, then by category name ascending for a stable order.
    """
    if not text:
        return []

    signals: list[DelaySignal] = []
    for category, entries in _PATTERNS.items():
        matched: list[str] = []
        for phrase, pattern in entries:
            if pattern.search(text):
                matched.append(phrase)
        if not matched:
            continue
        confidence = min(1.0, len(matched) / 3.0)
        signals.append(
            DelaySignal(
                category=category,
                confidence=confidence,
                matched_phrases=matched,
                suggested_activities=list(CATEGORY_ACTIVITIES[category]),
            )
        )

    signals.sort(key=lambda s: (-s.confidence, s.category))
    return signals


def detect_from_email(parsed: object) -> list[DelaySignal]:
    """Run :func:`detect_delays` over a parsed email's subject and body.

    Accepts a :class:`~app.modules.inbound_email.eml_parser.ParsedEmail`
    (duck-typed: any object exposing ``subject`` and ``body_text`` strings).
    The subject is searched alongside the body so a cause named only in the
    subject line is still caught.
    """
    subject = getattr(parsed, "subject", "") or ""
    body = getattr(parsed, "body_text", "") or ""
    return detect_delays(f"{subject}\n{body}")
