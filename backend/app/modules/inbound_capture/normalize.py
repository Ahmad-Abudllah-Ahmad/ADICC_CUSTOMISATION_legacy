# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure normalizer: any parsed inbound payload -> one canonical message shape.

Correspondence reaches a project from several places - a forwarded email, a
chat / generic webhook, an SMS gateway - and each arrives in its own ad-hoc
JSON. Before any of it can be persisted as an ``oe_correspondence`` row,
matched to a change, or threaded into a conversation, it has to be flattened to
a single predictable shape. This engine does exactly that and nothing else: it
takes an ALREADY-PARSED payload (the caller did the MIME / JSON / form parsing)
and maps it to an :class:`InboundMessage`.

Three channels are recognised - email, generic webhook (chat), and SMS - each
with its own field-name conventions, plus a :func:`normalize` dispatcher keyed
on the channel constant. Two cross-cutting helpers round it out:
:func:`normalize_subject` strips repeated reply / forward prefixes
(``Re:``/``Fwd:``/``Fw:``/``Aw:``) and collapses whitespace so a thread can be
matched by subject, and :func:`idempotency_key` derives a stable hex digest of
``(channel, external_id)`` so the same delivery captured twice does not create a
duplicate record.

The engine is relentlessly defensive: missing or blank fields fall back to safe
defaults, a slightly malformed payload never raises (it returns a best-effort
message), and anything it does not recognise at the top level of the payload is
preserved as a breadcrumb in ``raw_refs`` rather than silently dropped.
Timestamps are accepted either as a :class:`~datetime.datetime` or as an
ISO-8601 string (a trailing ``Z`` is tolerated); an unparseable timestamp falls
back to the Unix epoch in UTC so downstream code always has an aware datetime.

No database, no ORM, no ``app.*`` imports, no network - stdlib only - so it
unit-tests on the local Python 3.11 runner like the other pure engines. The
thin service / router layer (written separately) receives the channel POST,
parses the body, calls the matching normalizer, and persists the result as an
incoming correspondence row.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime

#: Channel constants. The dispatcher and the persistence layer key on these so
#: the spelling lives in exactly one place.
CHANNEL_EMAIL = "email"
CHANNEL_WEBHOOK = "webhook"
CHANNEL_SMS = "sms"

#: Fallback channel when a payload arrives with no usable channel hint. It is a
#: distinct token (not one of the known channels) so a caller can tell that the
#: channel was guessed rather than declared.
CHANNEL_UNKNOWN = "unknown"

#: Reply / forward subject prefixes stripped by :func:`normalize_subject`,
#: lower-cased for case-insensitive matching. Covers the common English and
#: German abbreviations seen on forwarded correspondence.
_REPLY_PREFIXES = ("re", "fwd", "fw", "aw")

#: Aware-UTC fallback for an absent or unparseable timestamp. Using the epoch
#: (rather than "now") keeps the function deterministic and side-effect free -
#: the same payload always yields the same message.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class AttachmentRef:
    """A pointer to one inbound attachment - never the bytes themselves.

    ``size_bytes`` is a non-negative integer (a missing / unparseable size
    resolves to 0). ``storage_hint`` is wherever the parsing layer already
    stashed the payload (an object-store key, a temp path, a content-id); it is
    opaque to this engine and ``None`` when not provided.
    """

    filename: str
    content_type: str
    size_bytes: int
    storage_hint: str | None


@dataclass(frozen=True)
class InboundMessage:
    """The single canonical shape every channel maps onto.

    ``recipients``, ``attachments`` and ``raw_refs`` are tuples so the message
    is hashable and cannot be mutated after capture. ``external_id`` is the
    channel's own identifier for the delivery (message-id, webhook event id, SMS
    id); it backs the idempotency key. ``sent_at`` is always an aware
    :class:`~datetime.datetime`. ``raw_refs`` carries breadcrumbs for anything
    the normalizer could not place into a typed field, so nothing is lost.
    """

    channel: str
    external_id: str
    sender: str
    recipients: tuple[str, ...]
    sent_at: datetime
    subject: str
    body: str
    attachments: tuple[AttachmentRef, ...]
    in_reply_to: str | None
    raw_refs: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# small, defensive coercion helpers
# ---------------------------------------------------------------------------


def _as_text(value: object) -> str:
    """Coerce any value to a stripped string; ``None`` becomes ``""``.

    Never raises - a value that cannot be stringified is unreachable for the
    JSON-shaped inputs this engine sees, but the guard keeps the contract total.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    try:
        return str(value).strip()
    except Exception:
        return ""


def _as_opt_text(value: object) -> str | None:
    """Like :func:`_as_text` but a blank result collapses to ``None``."""
    text = _as_text(value)
    return text or None


def _as_int(value: object) -> int:
    """Coerce to a non-negative int; anything unparseable becomes 0.

    Tolerates ints, floats and numeric strings (``"123"``, ``" 45 "``). A
    negative size is clamped to 0 - a byte count is never negative.
    """
    if isinstance(value, bool):  # bool is an int subclass; treat as no size
        return 0
    if isinstance(value, int):
        return value if value >= 0 else 0
    if isinstance(value, float):
        try:
            n = int(value)
        except (ValueError, OverflowError):
            return 0
        return n if n >= 0 else 0
    text = _as_text(value)
    if not text:
        return 0
    try:
        n = int(text)
    except ValueError:
        try:
            n = int(float(text))
        except (ValueError, OverflowError):
            return 0
    return n if n >= 0 else 0


def _first(payload: dict, *keys: str) -> object:
    """Return the first present, non-None value among *keys* in *payload*.

    Channel payloads spell the same idea differently (``from`` vs ``sender`` vs
    ``msisdn``); this picks the first one that exists so the normalizers can
    list their accepted aliases in priority order. Returns ``None`` when none of
    the keys are present.
    """
    if not isinstance(payload, dict):
        return None
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _coerce_recipients(value: object) -> tuple[str, ...]:
    """Normalize a recipients field to a tuple of clean address strings.

    Accepts a list / tuple of strings, or a single comma- or semicolon-
    separated string (``"a@x.com, b@y.com"``). Blank entries are dropped and
    order is preserved; duplicates are kept (the caller may care who was on the
    line twice). A scalar non-string is best-effort stringified.
    """
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            text = _as_text(item)
            if text:
                out.append(text)
        return tuple(out)
    text = _as_text(value)
    if not text:
        return ()
    parts = [p.strip() for p in text.replace(";", ",").split(",")]
    return tuple(p for p in parts if p)


def _coerce_dt(value: object) -> datetime:
    """Coerce a datetime-or-ISO-string to an aware UTC datetime.

    Accepts a :class:`~datetime.datetime` (naive is assumed UTC and stamped) or
    an ISO-8601 string parsed with :func:`datetime.fromisoformat`. A trailing
    ``Z`` (or ``z``) is tolerated by swapping it for ``+00:00`` before parsing,
    which 3.11's parser does not accept on its own. Anything missing or
    unparseable falls back to :data:`_EPOCH` so the caller always gets an aware
    datetime and the function never raises.
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    text = _as_text(value)
    if not text:
        return _EPOCH
    candidate = text
    if candidate[-1] in ("Z", "z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return _EPOCH
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _coerce_attachments(value: object) -> tuple[AttachmentRef, ...]:
    """Normalize an attachments list to a tuple of :class:`AttachmentRef`.

    Each element is expected to be a dict with ``filename`` /
    ``content_type`` / ``size`` style keys (several aliases accepted). Non-dict
    or empty elements are skipped. A nameless attachment with no content type
    and no size carries no information, so it is dropped rather than recorded as
    an empty ref. Never raises on a malformed element.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    out: list[AttachmentRef] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        filename = _as_text(_first(item, "filename", "name", "file_name"))
        content_type = _as_text(_first(item, "content_type", "contentType", "mime_type", "mimeType", "type"))
        size_bytes = _as_int(_first(item, "size_bytes", "size", "length", "bytes"))
        storage_hint = _as_opt_text(_first(item, "storage_hint", "storage_key", "path", "url", "content_id", "cid"))
        if not filename and not content_type and size_bytes == 0 and storage_hint is None:
            continue
        out.append(
            AttachmentRef(
                filename=filename,
                content_type=content_type,
                size_bytes=size_bytes,
                storage_hint=storage_hint,
            )
        )
    return tuple(out)


def _unrecognized_refs(payload: dict, recognized: set[str]) -> tuple[str, ...]:
    """Breadcrumb the payload keys a normalizer did not consume.

    Keeps a sorted ``key=repr`` note for every top-level key outside
    *recognized* so an unexpected provider field is visible downstream instead
    of being silently dropped. Sorted for determinism; values are length-capped
    so a huge field cannot bloat the record.
    """
    if not isinstance(payload, dict):
        return ()
    refs: list[str] = []
    for key in sorted(payload, key=str):
        if key in recognized:
            continue
        raw = payload[key]
        if raw is None:
            continue
        rendered = _as_text(raw)
        if not rendered:
            # Non-string truthy value (e.g. a nested dict) - record its repr.
            rendered = repr(raw)
        if len(rendered) > 200:
            rendered = rendered[:197] + "..."
        refs.append(f"{key}={rendered}")
    return tuple(refs)


# ---------------------------------------------------------------------------
# subject normalization
# ---------------------------------------------------------------------------


def normalize_subject(subject: str) -> str:
    """Strip repeated reply / forward prefixes and collapse whitespace.

    Removes any chain of leading ``Re:`` / ``Fwd:`` / ``Fw:`` / ``Aw:``
    prefixes (case-insensitive, each optionally followed by a bracketed count
    like ``Re[2]:``), then squeezes internal runs of whitespace to single
    spaces and trims the ends. Case of the surviving text is preserved. A blank
    or all-prefix subject normalizes to ``""``. Used for thread matching, so the
    output is the comparable form - the original display subject is kept on the
    message body separately by the caller.
    """
    text = _as_text(subject)
    if not text:
        return ""

    changed = True
    while changed:
        changed = False
        stripped = text.lstrip()
        head, sep, tail = stripped.partition(":")
        if not sep:
            break
        token = head.strip().lower()
        # Allow a bracketed / parenthesised counter, e.g. "re[2]" or "fw(3)".
        bracket = token.find("[")
        if bracket == -1:
            bracket = token.find("(")
        if bracket != -1:
            token = token[:bracket].strip()
        if token in _REPLY_PREFIXES:
            text = tail
            changed = True

    return " ".join(text.split())


# ---------------------------------------------------------------------------
# per-channel normalizers
# ---------------------------------------------------------------------------


def normalize_email(parsed: dict) -> InboundMessage:
    """Map an already-parsed ``.eml`` dict to an :class:`InboundMessage`.

    The MIME parsing has already happened upstream; *parsed* is a plain dict
    with the familiar header / body keys. Recognised keys (first alias wins):

    * sender: ``from`` / ``sender`` / ``from_address``
    * recipients: ``to`` (list or comma string); ``cc`` is folded in after ``to``
    * external id: ``message_id`` / ``message-id`` / ``id``
    * sent time: ``date`` / ``sent_at`` / ``timestamp``
    * subject: ``subject``
    * body: ``text`` / ``body`` / ``plain``
    * reply threading: ``in_reply_to`` / ``in-reply-to`` / ``references``
    * attachments: ``attachments`` (list of dicts)

    Anything else in the dict is preserved in ``raw_refs``. Missing fields take
    safe defaults; the function never raises.
    """
    payload = parsed if isinstance(parsed, dict) else {}

    sender = _as_text(_first(payload, "from", "sender", "from_address"))
    recipients = _coerce_recipients(_first(payload, "to", "recipients", "to_address"))
    cc = _coerce_recipients(_first(payload, "cc"))
    recipients = recipients + cc

    external_id = _as_text(_first(payload, "message_id", "message-id", "messageId", "id"))
    sent_at = _coerce_dt(_first(payload, "date", "sent_at", "timestamp"))
    subject = _as_text(_first(payload, "subject"))
    body = _as_text(_first(payload, "text", "body", "plain"))
    in_reply_to = _as_opt_text(_first(payload, "in_reply_to", "in-reply-to", "inReplyTo", "references"))
    attachments = _coerce_attachments(_first(payload, "attachments"))

    recognized = {
        "from",
        "sender",
        "from_address",
        "to",
        "recipients",
        "to_address",
        "cc",
        "message_id",
        "message-id",
        "messageId",
        "id",
        "date",
        "sent_at",
        "timestamp",
        "subject",
        "text",
        "body",
        "plain",
        "in_reply_to",
        "in-reply-to",
        "inReplyTo",
        "references",
        "attachments",
    }
    raw_refs = _unrecognized_refs(payload, recognized)

    return InboundMessage(
        channel=CHANNEL_EMAIL,
        external_id=external_id,
        sender=sender,
        recipients=recipients,
        sent_at=sent_at,
        subject=subject,
        body=body,
        attachments=attachments,
        in_reply_to=in_reply_to,
        raw_refs=raw_refs,
    )


def normalize_webhook(payload: dict, *, channel_hint: str | None = None) -> InboundMessage:
    """Map a generic chat / webhook JSON body to an :class:`InboundMessage`.

    Webhook shapes vary the most, so this accepts the widest alias set and
    tolerates almost everything missing. Recognised keys (first alias wins):

    * sender: ``sender`` / ``from`` / ``user`` / ``author`` / ``username``
    * recipients: ``recipients`` / ``to`` / ``channel`` / ``room``
    * external id: ``id`` / ``event_id`` / ``message_id`` / ``ts``
    * sent time: ``sent_at`` / ``timestamp`` / ``ts`` / ``time`` / ``date``
    * subject: ``subject`` / ``title`` / ``topic``
    * body: ``text`` / ``body`` / ``message`` / ``content``
    * reply threading: ``in_reply_to`` / ``thread_id`` / ``parent_id`` / ``thread_ts``
    * attachments: ``attachments`` / ``files``

    The stored channel is ``channel_hint`` when given (lets the caller record a
    concrete provider channel), otherwise the generic :data:`CHANNEL_WEBHOOK`.
    The hint itself is never treated as a payload field. Anything unrecognised in
    the body is preserved in ``raw_refs``. Never raises.
    """
    body_payload = payload if isinstance(payload, dict) else {}

    sender = _as_text(_first(body_payload, "sender", "from", "user", "author", "username"))
    recipients = _coerce_recipients(_first(body_payload, "recipients", "to", "channel", "room"))
    external_id = _as_text(_first(body_payload, "id", "event_id", "eventId", "message_id", "messageId", "ts"))
    sent_at = _coerce_dt(_first(body_payload, "sent_at", "timestamp", "ts", "time", "date"))
    subject = _as_text(_first(body_payload, "subject", "title", "topic"))
    body = _as_text(_first(body_payload, "text", "body", "message", "content"))
    in_reply_to = _as_opt_text(
        _first(body_payload, "in_reply_to", "inReplyTo", "thread_id", "threadId", "parent_id", "parentId", "thread_ts")
    )
    attachments = _coerce_attachments(_first(body_payload, "attachments", "files"))

    channel = _as_text(channel_hint) or CHANNEL_WEBHOOK

    recognized = {
        "sender",
        "from",
        "user",
        "author",
        "username",
        "recipients",
        "to",
        "channel",
        "room",
        "id",
        "event_id",
        "eventId",
        "message_id",
        "messageId",
        "ts",
        "sent_at",
        "timestamp",
        "time",
        "date",
        "subject",
        "title",
        "topic",
        "text",
        "body",
        "message",
        "content",
        "in_reply_to",
        "inReplyTo",
        "thread_id",
        "threadId",
        "parent_id",
        "parentId",
        "thread_ts",
        "attachments",
        "files",
    }
    raw_refs = _unrecognized_refs(body_payload, recognized)

    return InboundMessage(
        channel=channel,
        external_id=external_id,
        sender=sender,
        recipients=recipients,
        sent_at=sent_at,
        subject=subject,
        body=body,
        attachments=attachments,
        in_reply_to=in_reply_to,
        raw_refs=raw_refs,
    )


def normalize_sms(payload: dict) -> InboundMessage:
    """Map an SMS-gateway JSON body to an :class:`InboundMessage`.

    SMS has no subject and (almost) never an attachment, so those normalize to
    empty. Recognised keys (first alias wins):

    * sender: ``from`` / ``sender`` / ``msisdn`` / ``source``
    * recipients: ``to`` / ``recipient`` / ``destination``
    * external id: ``id`` / ``message_id`` / ``sms_id`` / ``sid``
    * sent time: ``sent_at`` / ``timestamp`` / ``date`` / ``received_at``
    * body: ``text`` / ``body`` / ``message``
    * attachments (MMS, rare): ``attachments`` / ``media``

    The subject is left blank. Anything unrecognised is preserved in
    ``raw_refs``. Never raises.
    """
    body_payload = payload if isinstance(payload, dict) else {}

    sender = _as_text(_first(body_payload, "from", "sender", "msisdn", "source"))
    recipients = _coerce_recipients(_first(body_payload, "to", "recipient", "destination"))
    external_id = _as_text(_first(body_payload, "id", "message_id", "messageId", "sms_id", "smsId", "sid"))
    sent_at = _coerce_dt(_first(body_payload, "sent_at", "timestamp", "date", "received_at"))
    body = _as_text(_first(body_payload, "text", "body", "message"))
    attachments = _coerce_attachments(_first(body_payload, "attachments", "media"))

    recognized = {
        "from",
        "sender",
        "msisdn",
        "source",
        "to",
        "recipient",
        "destination",
        "id",
        "message_id",
        "messageId",
        "sms_id",
        "smsId",
        "sid",
        "sent_at",
        "timestamp",
        "date",
        "received_at",
        "text",
        "body",
        "message",
        "attachments",
        "media",
    }
    raw_refs = _unrecognized_refs(body_payload, recognized)

    return InboundMessage(
        channel=CHANNEL_SMS,
        external_id=external_id,
        sender=sender,
        recipients=recipients,
        sent_at=sent_at,
        subject="",
        body=body,
        attachments=attachments,
        in_reply_to=None,
        raw_refs=raw_refs,
    )


# ---------------------------------------------------------------------------
# dispatcher + idempotency
# ---------------------------------------------------------------------------


def normalize(channel: str, payload: dict) -> InboundMessage:
    """Dispatch to the channel-specific normalizer by *channel*.

    Matching is case-insensitive and whitespace-tolerant against the channel
    constants. An unknown or blank channel falls through to the webhook
    normalizer (the most permissive shape) with the message's stored channel set
    to :data:`CHANNEL_UNKNOWN` when nothing usable was given, or to the supplied
    channel token when one was - so the dispatch never raises and the record
    still says where it came from.
    """
    token = _as_text(channel).lower()
    if token == CHANNEL_EMAIL:
        return normalize_email(payload)
    if token == CHANNEL_SMS:
        return normalize_sms(payload)
    if token == CHANNEL_WEBHOOK:
        return normalize_webhook(payload)
    # Unknown channel: parse with the permissive webhook shape but preserve the
    # caller's channel label (or mark it unknown) so the origin is not lost.
    hint = token or CHANNEL_UNKNOWN
    return normalize_webhook(payload, channel_hint=hint)


def idempotency_key(msg: InboundMessage) -> str:
    """Stable hex digest of ``(channel, external_id)`` for de-duplication.

    Two captures of the same delivery (a retried webhook, a re-imported email)
    share a channel and external id, so they collapse to the same key and the
    persistence layer can upsert instead of inserting a duplicate. The digest is
    over a delimited, channel-lower-cased pair using a separator that cannot
    appear in the inputs after normalization (a NUL byte), so distinct pairs can
    never collide by concatenation. Deterministic and pure - same message in,
    same key out.

    A message with a blank ``external_id`` still yields a key (over the empty
    id), but the caller should be aware such messages are not de-duplicable
    against each other; the service layer is expected to fall back to its own
    surrogate id in that case.
    """
    channel = _as_text(msg.channel).lower()
    external_id = _as_text(msg.external_id)
    digest = hashlib.sha256(f"{channel}\x00{external_id}".encode()).hexdigest()
    return digest


__all__ = [
    "CHANNEL_EMAIL",
    "CHANNEL_SMS",
    "CHANNEL_UNKNOWN",
    "CHANNEL_WEBHOOK",
    "AttachmentRef",
    "InboundMessage",
    "idempotency_key",
    "normalize",
    "normalize_email",
    "normalize_sms",
    "normalize_subject",
    "normalize_webhook",
]
