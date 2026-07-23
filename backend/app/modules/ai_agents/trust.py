# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Trust envelope - a standardized "trust wrapper" for AI agent outputs.

The single biggest barrier to AI adoption reported by construction teams is
trust: can an estimator rely on what the model said, and can they check it?
A free-form confidence sentence buried in prose (the ad-hoc approach in
``rate_benchmarker`` / ``progress_reporter`` today) is neither machine-readable
nor auditable. This module gives every agent ONE consistent, structured
"envelope" it can attach to any answer:

* a calibrated ``confidence`` in 0..1 (honest, never fabricated),
* a short ``rationale`` for that number,
* concrete ``sources`` cited by REAL id / path (never invented),
* ``what_would_increase_confidence`` - the missing inputs that would let the
  agent be more sure.

Design constraints (deliberate):

* Pure standard library only (dataclasses / enum / typing / json / re / math).
  No ``app.*`` import, no third-party dependency. The integrator wires this
  into ``base.AgentResult`` / ``StepRecord`` later; this module must import and
  unit-test in isolation.
* Never fabricate. Missing or malformed data collapses to ``None`` / an empty
  envelope - the helpers never guess a confidence or invent a source.
* Never raise from parsing. ``parse_envelope_from_text`` tolerates missing
  keys, wrong types and malformed JSON and always returns a usable pair.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "Source",
    "TrustEnvelope",
    "clamp_confidence",
    "make_envelope",
    "parse_envelope_from_text",
    "envelope_instructions",
    "TRUST_ENABLED_AGENTS",
]


# Recognised source ``kind`` values. This is advisory only - any non-empty
# string is accepted so an agent can cite a kind we have not enumerated yet -
# but it documents the vocabulary the UI knows how to render and link.
KNOWN_SOURCE_KINDS = (
    "document",
    "boq",
    "schedule",
    "cost_item",
    "rfi",
)


# Built-in agents whose answers are analytical judgments the reader must be able
# to trust and check, so the runner appends :func:`envelope_instructions` to
# their system prompt and parses the envelope back off their final answer.
# Mechanical drafters/classifiers (boq_drafter, cost_classifier, the *_drafter
# advisors, ...) are intentionally excluded: they emit structured output that may
# legitimately end in a JSON block, which must never be stripped as an envelope.
TRUST_ENABLED_AGENTS: frozenset[str] = frozenset(
    {
        "estimate_reviewer",
        "project_analyst",
        "rate_benchmarker",
        "progress_reporter",
        "document_analyst",
        "schedule_analyst",
        "compliance_checker",
        "cost_anomaly_reviewer",
        "tender_comparator",
        "risk_register_builder",
        "value_engineer",
    }
)


def clamp_confidence(v: Any) -> float | None:
    """Normalise a raw confidence value into ``[0.0, 1.0]`` or ``None``.

    Rules (never fabricate - an unusable input becomes ``None``):

    * ``None`` or a non-numeric value (string, list, NaN, infinity) -> ``None``.
    * a value already in ``0 <= v <= 1`` is kept as-is.
    * a value in ``1 < v <= 100`` is treated as a percentage and divided by 100.
    * anything else is clamped into the ``[0.0, 1.0]`` range (e.g. ``250`` is a
      percentage above 100 -> ``1.0``; a negative number -> ``0.0``).

    Booleans are rejected (``True``/``False`` are not a calibrated confidence)
    even though ``bool`` is a subclass of ``int``.
    """
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    if 0.0 <= f <= 1.0:
        return f
    if 1.0 < f <= 100.0:
        f = f / 100.0
    # Final clamp catches negatives and values above 100.
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


@dataclass(frozen=True)
class Source:
    """A single citation backing an agent's answer.

    Attributes:
        kind: what is being cited - e.g. ``document``, ``boq``, ``schedule``,
            ``cost_item``, ``rfi`` (see :data:`KNOWN_SOURCE_KINDS`).
        ref: the real identifier or path of the cited item (a row id, a file
            path, an RFI number). This must be something the user can actually
            open - agents are instructed never to invent it.
        label: optional human-readable label for display.
        score: optional relevance / match score in any scale the producer
            chose (e.g. a 0..1 similarity). Left untouched here.
    """

    kind: str
    ref: str
    label: str | None = None
    score: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict, omitting optional keys that are unset."""
        out: dict[str, Any] = {"kind": self.kind, "ref": self.ref}
        if self.label is not None:
            out["label"] = self.label
        if self.score is not None:
            out["score"] = self.score
        return out

    @classmethod
    def from_obj(cls, obj: Any) -> Source | None:
        """Build a :class:`Source` from an untrusted mapping, or ``None``.

        Tolerant by contract: a non-mapping, or one missing both a usable
        ``kind`` and ``ref``, yields ``None`` so a malformed entry is dropped
        rather than raising. ``kind`` / ``ref`` are coerced to stripped
        strings; ``score`` is coerced to ``float`` when finite, else dropped.
        """
        if not isinstance(obj, dict):
            return None
        kind = obj.get("kind")
        ref = obj.get("ref")
        kind_s = str(kind).strip() if kind is not None else ""
        ref_s = str(ref).strip() if ref is not None else ""
        if not kind_s and not ref_s:
            return None

        label = obj.get("label")
        label_s = str(label).strip() if isinstance(label, str) and label.strip() else None

        score_raw = obj.get("score")
        score_f: float | None
        if isinstance(score_raw, bool) or score_raw is None:
            score_f = None
        else:
            try:
                cand = float(score_raw)
                score_f = cand if math.isfinite(cand) else None
            except (TypeError, ValueError):
                score_f = None

        return cls(kind=kind_s, ref=ref_s, label=label_s, score=score_f)


@dataclass(frozen=True)
class TrustEnvelope:
    """A structured, auditable wrapper for an AI answer's trustworthiness.

    Every field is optional and defaults to an "I don't know / nothing to
    show" value, so an empty envelope is always valid and never overstates
    what the agent knows.

    Attributes:
        confidence: calibrated confidence in ``[0.0, 1.0]`` or ``None`` when
            the agent declined to commit to a number.
        rationale: short plain-text justification for the confidence.
        sources: tuple of :class:`Source` citations (real ids / paths).
        what_would_increase_confidence: the missing inputs that would let the
            agent be more certain.
        model: the model identifier that produced the answer, if known.
    """

    confidence: float | None = None
    rationale: str | None = None
    sources: tuple[Source, ...] = ()
    what_would_increase_confidence: str | None = None
    model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict (``json.dumps``-able with no defaults).

        ``sources`` is always present as a list (possibly empty) so consumers
        can iterate without a key check; the scalar optional fields are always
        present too, carrying ``null`` when unset.
        """
        return {
            "confidence": self.confidence,
            "rationale": self.rationale,
            "sources": [s.to_dict() for s in self.sources],
            "what_would_increase_confidence": self.what_would_increase_confidence,
            "model": self.model,
        }

    @classmethod
    def empty(cls, model: str | None = None) -> TrustEnvelope:
        """An envelope that asserts nothing (optionally tagged with a model)."""
        return cls(model=model)


def make_envelope(
    *,
    confidence: Any = None,
    rationale: Any = None,
    sources: Any = None,
    what_would_increase_confidence: Any = None,
    model: str | None = None,
) -> TrustEnvelope:
    """Construct a :class:`TrustEnvelope`, sanitising every input.

    This is the only blessed constructor for envelopes assembled from
    loosely-typed data (LLM output, API payloads). It never fabricates:

    * ``confidence`` is run through :func:`clamp_confidence` (bad -> ``None``).
    * ``rationale`` / ``what_would_increase_confidence`` are coerced to a
      stripped string, or ``None`` when blank / not a string.
    * ``sources`` accepts a single mapping/Source or an iterable of them; each
      entry is validated via :meth:`Source.from_obj` and malformed entries are
      dropped (not raised).
    """
    conf = clamp_confidence(confidence)
    rationale_s = _clean_text(rationale)
    wwic_s = _clean_text(what_would_increase_confidence)
    src_tuple = _coerce_sources(sources)
    model_s = model.strip() if isinstance(model, str) and model.strip() else None
    return TrustEnvelope(
        confidence=conf,
        rationale=rationale_s,
        sources=src_tuple,
        what_would_increase_confidence=wwic_s,
        model=model_s,
    )


def _clean_text(value: Any) -> str | None:
    """Coerce ``value`` to a non-empty stripped string, else ``None``."""
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _coerce_sources(value: Any) -> tuple[Source, ...]:
    """Turn loose input into a tuple of valid :class:`Source` objects.

    Accepts ``None`` (-> empty), a single :class:`Source` or mapping, or any
    iterable of those. Strings are intentionally NOT treated as iterables of
    characters. Malformed entries are silently dropped.
    """
    if value is None:
        return ()
    if isinstance(value, Source):
        return (value,)
    if isinstance(value, dict):
        one = Source.from_obj(value)
        return (one,) if one is not None else ()
    if isinstance(value, (str, bytes)):
        return ()

    out: list[Source] = []
    try:
        iterator = iter(value)
    except TypeError:
        return ()
    for item in iterator:
        if isinstance(item, Source):
            out.append(item)
            continue
        built = Source.from_obj(item)
        if built is not None:
            out.append(built)
    return tuple(out)


# A trailing fenced ```json ... ``` block. ``re.DOTALL`` lets the body span
# lines; the trailing ``\s*$`` anchors it to the very end of the message so we
# only ever strip the LAST block, never JSON the model used mid-answer.
_FENCED_JSON_RE = re.compile(
    r"```(?:json)?\s*(?P<body>\{.*\})\s*```\s*$",
    re.DOTALL | re.IGNORECASE,
)


def parse_envelope_from_text(
    text: str,
    model: str | None = None,
) -> tuple[str, TrustEnvelope]:
    """Split a trailing trust-envelope JSON block off an agent's reply.

    Looks for a trailing fenced ```json ... ``` block (the format
    :func:`envelope_instructions` asks the model to emit) and, failing that,
    a bare trailing ``{...}`` object. The JSON is expected to look like::

        {"confidence": 0.8,
         "rationale": "...",
         "sources": [{"kind": "boq", "ref": "..."}],
         "what_would_increase_confidence": "..."}

    Returns ``(text_without_that_block, envelope)``. The returned text has the
    matched block removed and trailing whitespace trimmed. On ANY failure
    (no block found, malformed JSON, non-object JSON) the ORIGINAL text is
    returned unchanged alongside an empty envelope. This function never raises.

    Args:
        text: the full agent reply, possibly ending with an envelope block.
        model: model id to stamp onto the parsed (or empty) envelope.
    """
    if not isinstance(text, str) or not text.strip():
        return (text if isinstance(text, str) else "", TrustEnvelope.empty(model))

    match = _FENCED_JSON_RE.search(text)
    if match is not None:
        body = match.group("body")
        start, end = match.span()
    else:
        body, start, end = _find_trailing_object(text)

    if body is None:
        return (text, TrustEnvelope.empty(model))

    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        return (text, TrustEnvelope.empty(model))

    if not isinstance(parsed, dict):
        return (text, TrustEnvelope.empty(model))

    envelope = make_envelope(
        confidence=parsed.get("confidence"),
        rationale=parsed.get("rationale"),
        sources=parsed.get("sources"),
        what_would_increase_confidence=parsed.get("what_would_increase_confidence"),
        model=model,
    )
    cleaned = (text[:start] + text[end:]).rstrip()
    return (cleaned, envelope)


def _find_trailing_object(text: str) -> tuple[str | None, int, int]:
    """Locate a bare ``{...}`` object at the very end of ``text``.

    Scans backward from the last ``}``, balancing braces while ignoring any
    inside double-quoted strings (honouring backslash escapes), to find the
    matching ``{``. Returns ``(body, start, end)`` where ``body`` is the raw
    object substring, or ``(None, -1, -1)`` when the tail is not a balanced
    object (e.g. trailing prose after the close brace).
    """
    stripped = text.rstrip()
    if not stripped.endswith("}"):
        return (None, -1, -1)

    end = len(stripped)
    depth = 0
    in_str = False
    escaped = False
    start = -1
    for i in range(end - 1, -1, -1):
        ch = stripped[i]
        if in_str:
            # Walking backward: a quote closes the (reversed) string only when
            # it is not escaped by a preceding backslash.
            if ch == '"' and not _escaped_backward(stripped, i):
                in_str = False
            continue
        if ch == '"':
            in_str = True
            continue
        if ch == "}":
            depth += 1
        elif ch == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    if start == -1:
        return (None, -1, -1)
    return (stripped[start:end], start, end)


def _escaped_backward(text: str, idx: int) -> bool:
    """Return True if the char at ``idx`` is escaped by an odd backslash run."""
    backslashes = 0
    j = idx - 1
    while j >= 0 and text[j] == "\\":
        backslashes += 1
        j -= 1
    return backslashes % 2 == 1


def envelope_instructions() -> str:
    """System-prompt snippet telling a model how to emit a trust envelope.

    Append this to an agent's ``system_prompt``. It is plain ASCII English and
    instructs the model to END its reply with a single fenced ```json``` block
    of the exact envelope shape, to set ``confidence`` honestly in ``0..1``, to
    cite sources only by REAL id / path (never invented), and to state what
    would increase its confidence. The wording mirrors what
    :func:`parse_envelope_from_text` can read back.
    """
    return (
        "TRUST ENVELOPE (required):\n"
        "After your normal answer, end your reply with EXACTLY ONE fenced code "
        "block tagged json that contains a single JSON object describing how "
        "much the reader should trust this answer. Put nothing after that "
        "block. Use this exact shape:\n"
        "```json\n"
        "{\n"
        '  "confidence": 0.0,\n'
        '  "rationale": "one or two sentences on why this confidence",\n'
        '  "sources": [\n'
        '    {"kind": "boq", "ref": "real-id-or-path", "label": "optional"}\n'
        "  ],\n"
        '  "what_would_increase_confidence": "the specific inputs or checks '
        'that would let you be more sure"\n'
        "}\n"
        "```\n"
        "Rules:\n"
        "- Set confidence honestly as a number between 0 and 1 (0 = a guess, "
        "1 = certain). Do not inflate it. If you are unsure, say so with a low "
        "number and explain why in the rationale.\n"
        "- Cite sources only by their REAL identifier or path that the reader "
        "can actually open (a record id, a file path, an RFI number). NEVER "
        "invent a source, id, or path. If you used no concrete source, return "
        "an empty sources list.\n"
        "- kind should be one of: document, boq, schedule, cost_item, rfi "
        "(or another short, accurate label).\n"
        "- what_would_increase_confidence must name the missing data or checks "
        "that would make the answer more reliable.\n"
        "- Output valid JSON only inside the block: double-quoted keys and "
        "strings, no trailing commas, no comments."
    )
