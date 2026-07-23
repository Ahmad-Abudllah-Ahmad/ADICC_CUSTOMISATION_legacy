# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure engine that turns a spoken/typed note into a structured draft.

This is the shared voice-to-structured-entry brain used by the voice module.
A site worker speaks (or types) a rough note in whatever language they have;
this module turns that raw text into a clean, structured DRAFT shaped for the
target the user chose - a daily-diary note, a defect/punch item, or a task -
which the user then reviews and confirms before anything is saved.

Design rules this module keeps (mirroring ``phonelog.transcription``):

* AI suggests, a human confirms. Everything here is a *draft*; the caller
  presents it for review and only the reviewed values are saved downstream.
* AI is optional and degrades gracefully. When an LLM extraction ran, its
  fields are cleaned and used; when it did not (no provider, or a failed call),
  a deterministic heuristic fills the same fields from the raw text so the
  feature stays usable with zero AI configured.
* Pure and stdlib-only. No I/O, no database, no framework imports, no network.
  Every function here is independently unit-testable. The provider-calling and
  transcription glue lives in ``voice.service`` / ``phonelog.transcription``.

The output ``fields`` are plain strings keyed by field name so the same generic
shape serves every target; the frontend maps those field values onto each
feature's own create payload. Enum-valued fields are always clamped to the
exact set the downstream schema accepts, so a confirmed draft can never carry a
value the target's Pydantic model would reject.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Target-type identifiers. These are the contract with the frontend and the
# router; keep them stable. Each maps to a real create-schema shape:
#   diary_note -> daily_diary.DiaryEntryCreate (entry_type/title/description)
#   defect     -> punchlist.PunchItemCreate    (title/description/trade/...)
#   task       -> tasks.TaskCreate             (title/description/priority/...)
TARGET_DIARY_NOTE = "diary_note"
TARGET_DEFECT = "defect"
TARGET_TASK = "task"

# Longest raw note we structure. A spoken site note is short; anything past this
# is almost certainly a paste and only the head carries the entry, so we clip to
# keep the prompt (and any bill) bounded. Mirrors the transcript cap in phonelog.
MAX_TEXT_CHARS: int = 12000

# Per-kind output caps so a draft field can never blow past the target column.
_TITLE_MAX = 240
_TEXT_MAX = 400
_LONGTEXT_MAX = 5000
_DATE_MAX = 10

# ISO date the LLM is asked to emit for date fields.
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_SENTENCE_SPLIT = re.compile(r"[.!?\n]+")
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class FieldSpec:
    """One field of a target draft.

    ``kind`` drives both the extraction prompt and the cleaner:
        - ``text``     - a short single-line value (clamped to ``_TEXT_MAX``)
        - ``longtext`` - a multi-line value (clamped to ``_LONGTEXT_MAX``)
        - ``title``    - a short headline (clamped to ``_TITLE_MAX``)
        - ``enum``     - clamped to one of ``choices`` (else ``default``)
        - ``date``     - an ISO ``YYYY-MM-DD`` string, or "" when none is stated

    ``hints`` powers the no-LLM heuristic for ``enum`` fields: an ordered tuple
    of ``(choice, keywords)`` scanned most-specific first, so a note mentioning
    "urgent" resolves to the urgent choice before the default. It is never used
    when an LLM extraction is available.
    """

    name: str
    kind: str
    prompt: str
    choices: tuple[str, ...] = ()
    default: str = ""
    hints: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True)
class TargetSpec:
    """The full shape of one target draft plus its domain framing."""

    target_type: str
    label: str
    framing: str
    fields: tuple[FieldSpec, ...]

    def field_names(self) -> tuple[str, ...]:
        """Return the ordered field names of this target."""
        return tuple(f.name for f in self.fields)


# ── Target registry ──────────────────────────────────────────────────────────

_DIARY_ENTRY_TYPES = (
    "general",
    "delivery",
    "visitor",
    "event",
    "completion",
    "incident_summary",
    "inspection_summary",
    "photo_note",
)

_DEFECT_CATEGORIES = (
    "general",
    "structural",
    "mechanical",
    "electrical",
    "architectural",
    "fire_safety",
    "plumbing",
    "finishing",
    "hvac",
    "exterior",
    "landscaping",
)

_DEFECT_PRIORITIES = ("low", "medium", "high", "critical")
_TASK_PRIORITIES = ("low", "normal", "high", "urgent")


TARGET_SPECS: dict[str, TargetSpec] = {
    TARGET_DIARY_NOTE: TargetSpec(
        target_type=TARGET_DIARY_NOTE,
        label="Daily diary note",
        framing=(
            "You are helping a construction site worker turn a spoken or typed note into a "
            "daily site-diary entry (what happened on site today: work done, deliveries, "
            "visitors, events)."
        ),
        fields=(
            FieldSpec(
                name="entry_type",
                kind="enum",
                prompt="the kind of entry this note is",
                choices=_DIARY_ENTRY_TYPES,
                default="general",
                hints=(
                    ("incident_summary", ("incident", "injury", "accident", "near miss", "near-miss")),
                    ("inspection_summary", ("inspection", "inspected", "inspector")),
                    ("delivery", ("delivery", "delivered", "arrived", "truck", "unloaded")),
                    ("visitor", ("visitor", "visited", "client came", "site visit")),
                    ("completion", ("completed", "finished", "poured", "handed over", "signed off")),
                    ("event", ("meeting", "event", "toolbox talk", "briefing")),
                ),
            ),
            FieldSpec(
                name="title",
                kind="title",
                prompt="a short headline for the entry (a few words)",
            ),
            FieldSpec(
                name="description",
                kind="longtext",
                prompt="the full note, tidied into clear sentences",
            ),
        ),
    ),
    TARGET_DEFECT: TargetSpec(
        target_type=TARGET_DEFECT,
        label="Defect / punch item",
        framing=(
            "You are helping a construction site worker log a defect or snag (something built "
            "wrong or incomplete that needs fixing before handover) from a spoken or typed note."
        ),
        fields=(
            FieldSpec(
                name="title",
                kind="title",
                prompt="a short headline naming the defect",
            ),
            FieldSpec(
                name="description",
                kind="longtext",
                prompt="what is wrong and what needs doing, in clear sentences",
            ),
            FieldSpec(
                name="location",
                kind="text",
                prompt="where on site the defect is (building, level, room, gridline), or empty",
            ),
            FieldSpec(
                name="trade",
                kind="text",
                prompt="the trade responsible (e.g. electrical, plumbing), or empty if unclear",
            ),
            FieldSpec(
                name="category",
                kind="enum",
                prompt="the work category of the defect",
                choices=_DEFECT_CATEGORIES,
                default="general",
                hints=(
                    ("fire_safety", ("fire", "smoke", "sprinkler", "fire seal", "fire stop", "firestop")),
                    ("electrical", ("electric", "socket", "wiring", "cable", "conduit", "light", "power")),
                    ("plumbing", ("pipe", "leak", "plumb", "drain", "water", "tap", "sanitary")),
                    ("hvac", ("hvac", "air conditioning", "ventilation", "ahu", "ductwork")),
                    ("mechanical", ("duct", "pump", "mechanical", "boiler", "valve")),
                    ("structural", ("crack", "beam", "column", "slab", "structural", "concrete", "rebar", "steel")),
                    ("architectural", ("door", "window", "wall", "partition", "ceiling", "glazing")),
                    ("finishing", ("paint", "tile", "plaster", "finish", "skirting", "render", "grout")),
                    ("exterior", ("facade", "roof", "cladding", "external", "exterior", "gutter")),
                    ("landscaping", ("landscap", "paving", "garden", "planting", "kerb", "curb")),
                ),
            ),
            FieldSpec(
                name="priority",
                kind="enum",
                prompt="how urgent the fix is",
                choices=_DEFECT_PRIORITIES,
                default="medium",
                hints=(
                    ("critical", ("critical", "danger", "unsafe", "collapse", "hazard", "emergency")),
                    ("high", ("urgent", "high", "asap", "immediately", "safety", "important")),
                    ("low", ("minor", "cosmetic", "low", "small", "snag", "whenever")),
                ),
            ),
        ),
    ),
    TARGET_TASK: TargetSpec(
        target_type=TARGET_TASK,
        label="Task",
        framing=(
            "You are helping a construction worker turn a spoken or typed note into an action "
            "item / task (something someone needs to do), for a site task board."
        ),
        fields=(
            FieldSpec(
                name="title",
                kind="title",
                prompt="a short, action-oriented headline for the task",
            ),
            FieldSpec(
                name="description",
                kind="longtext",
                prompt="any detail about what needs doing, in clear sentences",
            ),
            FieldSpec(
                name="priority",
                kind="enum",
                prompt="the task priority",
                choices=_TASK_PRIORITIES,
                default="normal",
                hints=(
                    ("urgent", ("urgent", "asap", "immediately", "critical", "today", "now")),
                    ("high", ("high", "important", "priority", "soon", "tomorrow")),
                    ("low", ("low", "minor", "whenever", "sometime", "no rush")),
                ),
            ),
            FieldSpec(
                name="due_date",
                kind="date",
                prompt=("a due date as YYYY-MM-DD, ONLY if an explicit calendar date is stated; otherwise empty"),
            ),
        ),
    ),
}


def target_spec(target_type: str) -> TargetSpec | None:
    """Return the :class:`TargetSpec` for ``target_type``, or None when unknown."""
    return TARGET_SPECS.get((target_type or "").strip())


def target_types() -> tuple[str, ...]:
    """Return the tuple of known target-type identifiers."""
    return tuple(TARGET_SPECS.keys())


# ── Language handling (for translation) ───────────────────────────────────────

# The trade's working language is passed as a UI locale code; map the common
# ones to an English name the model understands. An unknown code degrades to a
# generic instruction rather than failing, so a new locale never breaks voice.
_LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "ru": "Russian",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "pl": "Polish",
    "cs": "Czech",
    "da": "Danish",
    "fi": "Finnish",
    "no": "Norwegian",
    "sv": "Swedish",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "ar": "Arabic",
    "bg": "Bulgarian",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ro": "Romanian",
    "hu": "Hungarian",
    "el": "Greek",
    "he": "Hebrew",
    "hi": "Hindi",
    "id": "Indonesian",
    "vi": "Vietnamese",
}


def language_name(code: str | None) -> str | None:
    """Return the English language name for a UI locale code, or None.

    Accepts a bare code ("de") or a region-tagged one ("de-CH", "pt_BR"); only
    the primary subtag is used. None/blank/unknown returns None so the caller
    can omit the translation instruction entirely.
    """
    if not code:
        return None
    primary = re.split(r"[-_]", code.strip())[0].lower()
    return _LANGUAGE_NAMES.get(primary)


# ── Text cleaners (pure) ──────────────────────────────────────────────────────


def clip_text(value: Any, limit: int) -> str:
    """Coerce ``value`` to a single-line trimmed string capped at ``limit``."""
    if not isinstance(value, str):
        return ""
    collapsed = _WHITESPACE.sub(" ", value).strip()
    return collapsed[:limit].strip()


def clip_longtext(value: Any, limit: int = _LONGTEXT_MAX) -> str:
    """Coerce ``value`` to a trimmed multi-line string capped at ``limit``.

    Internal newlines are preserved (site notes are often bulleted), but runs of
    spaces/tabs within a line are collapsed and leading/trailing blank lines are
    stripped.
    """
    if not isinstance(value, str):
        return ""
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in value.replace("\r\n", "\n").split("\n")]
    text = "\n".join(lines).strip()
    return text[:limit].strip()


def clamp_enum(value: Any, choices: tuple[str, ...], default: str) -> str:
    """Clamp ``value`` to one of ``choices`` (case-insensitive), else ``default``.

    Tolerates the shapes an LLM realistically returns: an exact choice, a
    different case, or a choice with spaces where the canonical value uses
    underscores ("fire safety" -> "fire_safety"). Anything unmatched falls back
    to ``default`` so a downstream Pydantic pattern can never reject the value.
    """
    if not isinstance(value, str):
        return default
    key = value.strip().lower()
    if not key:
        return default
    normalized = key.replace(" ", "_").replace("-", "_")
    for choice in choices:
        if normalized == choice.lower():
            return choice
    return default


def normalize_date(value: Any) -> str:
    """Return an ISO ``YYYY-MM-DD`` date found in ``value``, or "".

    Only accepts a genuine ISO date; a vague timeframe the model may echo
    ("next week", "Friday") yields "" so the draft never carries an unparseable
    due date the target schema would reject.
    """
    if not isinstance(value, str):
        return ""
    match = _ISO_DATE_RE.search(value)
    if not match:
        return ""
    year, month, day = match.group(1), match.group(2), match.group(3)
    if not ("01" <= month <= "12") or not ("01" <= day <= "31"):
        return ""
    return f"{year}-{month}-{day}"[:_DATE_MAX]


def clean_field(spec_field: FieldSpec, value: Any) -> str:
    """Clean one raw value into the exact string shape ``spec_field`` requires."""
    if spec_field.kind == "enum":
        return clamp_enum(value, spec_field.choices, spec_field.default)
    if spec_field.kind == "date":
        return normalize_date(value)
    if spec_field.kind == "longtext":
        return clip_longtext(value)
    if spec_field.kind == "title":
        return clip_text(value, _TITLE_MAX)
    return clip_text(value, _TEXT_MAX)


# ── Heuristic fallback (no LLM) ───────────────────────────────────────────────


def _first_sentence(text: str, limit: int) -> str:
    """Return the first sentence of ``text`` trimmed to ``limit`` chars."""
    stripped = (text or "").strip()
    if not stripped:
        return ""
    first = _SENTENCE_SPLIT.split(stripped, maxsplit=1)[0].strip()
    chosen = first or stripped
    return clip_text(chosen, limit)


def _enum_from_hints(spec_field: FieldSpec, text_lower: str) -> str:
    """Resolve an enum field from keyword hints, most-specific first."""
    for choice, keywords in spec_field.hints:
        if any(keyword in text_lower for keyword in keywords):
            return choice
    return spec_field.default


def heuristic_fields(spec: TargetSpec, text: str) -> dict[str, str]:
    """Build a best-effort draft from raw text with no LLM.

    Deterministic and dependency-free: the first sentence becomes the title, the
    whole note becomes the description/long field, enum fields are keyword-matched
    (falling back to their default), and free-text / date fields are left empty
    because they cannot be reliably pulled out without a model. The user reviews
    and completes the draft, so an empty field is safe - a wrong guess is worse.
    """
    text = (text or "").strip()
    text_lower = text.lower()
    out: dict[str, str] = {}
    for spec_field in spec.fields:
        if spec_field.kind == "enum":
            out[spec_field.name] = _enum_from_hints(spec_field, text_lower)
        elif spec_field.kind == "title":
            out[spec_field.name] = _first_sentence(text, _TITLE_MAX)
        elif spec_field.kind == "longtext":
            out[spec_field.name] = clip_longtext(text)
        else:
            # Free text (location/trade) and dates need real understanding; leave
            # them for the user rather than guessing wrong.
            out[spec_field.name] = ""
    return out


# ── LLM-result cleaning ───────────────────────────────────────────────────────


def clean_llm_fields(spec: TargetSpec, llm_result: dict[str, Any]) -> dict[str, str]:
    """Clean an LLM extraction into the target's exact field shape.

    Reads only the keys the target defines; any extra keys the model returned are
    ignored, and any the model omitted fall back to the field default (enum) or ""
    (everything else) via :func:`clean_field`.
    """
    fields_obj = llm_result.get("fields")
    source = fields_obj if isinstance(fields_obj, dict) else llm_result
    out: dict[str, str] = {}
    for spec_field in spec.fields:
        out[spec_field.name] = clean_field(spec_field, source.get(spec_field.name))
    return out


def _refined_text(llm_result: dict[str, Any] | None, fallback: str) -> str:
    """Return the model's cleaned/translated prose, or the raw text as fallback."""
    if isinstance(llm_result, dict):
        refined = llm_result.get("refined_text")
        if isinstance(refined, str) and refined.strip():
            return clip_longtext(refined, _LONGTEXT_MAX)
    return clip_longtext(fallback, _LONGTEXT_MAX)


def draft_confidence(spec: TargetSpec, llm_result: dict[str, Any] | None, fields: dict[str, str]) -> float | None:
    """Confidence (0-1) for the structured draft, or None when no LLM ran.

    A model-reported ``confidence`` wins when present and in range; otherwise a
    small heuristic starts at 0.5 and rewards each non-empty, non-default field so
    a thin extraction reads as lower confidence. None is returned only when no
    extraction ran at all (``llm_result is None``), matching phonelog.
    """
    if llm_result is None:
        return None
    raw = llm_result.get("confidence")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return round(max(0.0, min(1.0, float(raw))), 2)

    score = 0.5
    populated = 0
    for spec_field in spec.fields:
        value = fields.get(spec_field.name, "")
        if not value:
            continue
        if spec_field.kind == "enum" and value == spec_field.default:
            continue
        populated += 1
    score += min(0.4, 0.1 * populated)
    return round(min(1.0, score), 2)


def assemble_draft(
    *,
    spec: TargetSpec,
    llm_result: dict[str, Any] | None,
    text: str,
    detected_language_hint: str | None = None,
) -> dict[str, Any]:
    """Assemble the structured draft returned to the caller.

    Pure and deterministic. When ``llm_result`` is a dict (the extraction ran)
    its fields are cleaned and used; when it is None (no provider, or the call
    failed) the deterministic :func:`heuristic_fields` fill the same shape and
    ``ai_generated`` is False so the UI can be honest that only the fallback ran.
    """
    ai_generated = isinstance(llm_result, dict)
    if ai_generated:
        fields = clean_llm_fields(spec, llm_result)  # type: ignore[arg-type]
        # An LLM that returned nothing usable for the headline still gets a
        # sensible title from the raw note rather than an empty one.
        if not fields.get("title") and any(f.name == "title" for f in spec.fields):
            fields["title"] = _first_sentence(text, _TITLE_MAX)
    else:
        fields = heuristic_fields(spec, text)

    detected = None
    if isinstance(llm_result, dict):
        raw_detected = llm_result.get("detected_language")
        if isinstance(raw_detected, str) and raw_detected.strip():
            detected = raw_detected.strip()[:40]
    if not detected and detected_language_hint:
        detected = detected_language_hint[:40]

    return {
        "target_type": spec.target_type,
        "fields": fields,
        "refined_text": _refined_text(llm_result, text),
        "confidence": draft_confidence(spec, llm_result, fields),
        "ai_generated": ai_generated,
        "detected_language": detected,
    }


# ── Prompt building ───────────────────────────────────────────────────────────


def structuring_system_prompt(spec: TargetSpec, target_language: str | None) -> str:
    """Build the system prompt for the structured-draft extraction pass."""
    lang = language_name(target_language)
    lang_clause = (
        f" Write every output field value in {lang}, translating if the note is in another language." if lang else ""
    )
    return (
        f"{spec.framing} Extract only what the note actually says. Never invent facts, names, "
        f"dates, locations, or trades that are not stated. If something is not in the note, leave "
        f"that field empty (or use the most neutral option for a category)." + lang_clause + " "
        "Respond with a single JSON object and nothing else."
    )


def build_structuring_prompt(spec: TargetSpec, text: str, target_language: str | None) -> str:
    """Build the user prompt describing the exact JSON fields to return."""
    clipped = (text or "").strip()
    if len(clipped) > MAX_TEXT_CHARS:
        clipped = clipped[:MAX_TEXT_CHARS] + "\n[note truncated]"

    field_lines: list[str] = []
    for spec_field in spec.fields:
        if spec_field.kind == "enum":
            options = ", ".join(spec_field.choices)
            detail = f'{spec_field.prompt}. One of exactly: {options}. Default "{spec_field.default}".'
        elif spec_field.kind == "date":
            detail = spec_field.prompt
        else:
            detail = spec_field.prompt
        field_lines.append(f'- "{spec_field.name}": {detail}')

    lang = language_name(target_language)
    lang_note = f" All field values must be written in {lang}." if lang else ""

    return (
        "Read the site note below and return a JSON object with exactly these keys:\n"
        '- "fields": an object with these keys:\n'
        + "\n".join(f"  {line}" for line in field_lines)
        + '\n- "refined_text": the note rewritten as clean, clear prose'
        + (f" in {lang}" if lang else "")
        + ".\n"
        '- "detected_language": the language the original note was spoken/written in.\n'
        '- "confidence": a number between 0 and 1 for how well this draft reflects the note.\n'
        "Use only information present in the note. Do not add anything that was not said."
        + lang_note
        + '\n\nNote:\n"""\n'
        + clipped
        + '\n"""'
    )
