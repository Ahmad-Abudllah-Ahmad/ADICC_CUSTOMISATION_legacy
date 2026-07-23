# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""International, edge-case-safe helpers for notification analytics.

This module is a pure, database-free layer that turns raw notification
counts into numbers and plain-language sentences that read the same for a
site engineer anywhere in the world. It exists so dashboards, digests and
reports never have to hand-roll the same fragile arithmetic (and never hit
a divide-by-zero, a ``NaN`` or a stray 500) when nothing has been sent yet.

Design rules honoured here:

* International first. No locale is hardcoded. Timestamps are emitted as
  ISO 8601 (UTC), and channel / status words localise to English, German
  and Russian with an English fallback for any unknown language or term.
* Clarity over cleverness. Every rate ships with a one-line explainer that
  says, in plain words, exactly how it was derived and which components fed
  it. A number a reader cannot explain to a colleague is not done.
* Edge cases are values, not crashes. Division by zero, empty inputs and
  impossible combinations resolve to a well-defined value or a clean
  ``ValueError``. Rates always land inside [0, 1] (and [0, 100] as percent).

The vocabulary mirrors the rest of the module exactly: channels come from
:class:`~app.modules.notifications.schemas.PreferenceRequest`
(``inapp`` / ``email`` / ``webhook`` / ``none``), read status from the
``is_read`` flag on :class:`~app.modules.notifications.models.Notification`,
and dispatch outcomes from
:meth:`~app.modules.notifications.service.NotificationService.enqueue_or_dispatch`
(``dispatched`` / ``queued`` / ``suppressed``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# ── Canonical vocabulary (mirrors models / schemas / service) ─────────────

#: Delivery channels a preference can target. Same order and spelling as the
#: ``PreferenceRequest.channel`` pattern in ``schemas.py``.
CHANNELS: tuple[str, ...] = ("inapp", "email", "webhook", "none")

#: Read states of an in-app notification, derived from ``Notification.is_read``.
READ_STATUSES: tuple[str, ...] = ("read", "unread")

#: Outcomes returned by ``NotificationService.enqueue_or_dispatch``.
DISPATCH_STATUSES: tuple[str, ...] = ("dispatched", "queued", "suppressed")

#: Digest cadences accepted by ``PreferenceRequest.digest``.
DIGEST_CADENCES: tuple[str, ...] = ("realtime", "hourly", "daily")

#: Bucket used when a value does not match any known term.
UNKNOWN: str = "unknown"

#: Languages with first-class translations. Anything else falls back to English.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "de", "ru")


# ── Localization tables (en / de / ru, English fallback) ──────────────────
#
# Kept as plain data so adding a language is a dict edit, never a code change.
# Only plain letters and hyphens are used; no long dashes, smart quotes or
# zero-width characters ever appear in a user-facing string here.

_LOCALIZED: dict[str, dict[str, dict[str, str]]] = {
    "channel": {
        "inapp": {"en": "In-app", "de": "In der App", "ru": "V prilozhenii"},
        "email": {"en": "Email", "de": "E-Mail", "ru": "Elektronnaya pochta"},
        "webhook": {"en": "Webhook", "de": "Webhook", "ru": "Veb-khuk"},
        "none": {"en": "Off", "de": "Aus", "ru": "Vyklyucheno"},
    },
    "read_status": {
        "read": {"en": "Read", "de": "Gelesen", "ru": "Prochitano"},
        "unread": {"en": "Unread", "de": "Ungelesen", "ru": "Neprochitano"},
    },
    "dispatch_status": {
        "dispatched": {"en": "Sent now", "de": "Sofort gesendet", "ru": "Otpravleno srazu"},
        "queued": {"en": "Queued for digest", "de": "Fuer Zusammenfassung eingereiht", "ru": "V ocheredi na daydzhest"},
        "suppressed": {"en": "Suppressed", "de": "Unterdrueckt", "ru": "Podavleno"},
    },
    "cadence": {
        "realtime": {"en": "Realtime", "de": "Echtzeit", "ru": "V realnom vremeni"},
        "hourly": {"en": "Hourly", "de": "Stuendlich", "ru": "Ezhechasno"},
        "daily": {"en": "Daily", "de": "Taeglich", "ru": "Ezhednevno"},
    },
}


def normalize_language(lang: str | None) -> str:
    """Return a supported language code, defaulting to English.

    Accepts region-tagged codes such as ``en-US`` or ``de_AT`` and keeps only
    the base language. Unknown or empty values resolve to ``"en"`` so the
    caller never has to guard the input.

    Args:
        lang: A language tag, possibly region-qualified or ``None``.

    Returns:
        One of :data:`SUPPORTED_LANGUAGES`.
    """
    if not lang:
        return "en"
    base = lang.strip().lower().replace("_", "-").split("-", 1)[0]
    return base if base in SUPPORTED_LANGUAGES else "en"


def localize(kind: str, term: str | None, lang: str | None = "en") -> str:
    """Localize a single vocabulary term with an English fallback.

    Resolution order: the requested language, then English, then the raw term
    itself so an unrecognised value is still readable rather than blank.

    Args:
        kind: One of ``"channel"``, ``"read_status"``, ``"dispatch_status"``
            or ``"cadence"``.
        term: The canonical term to translate (for example ``"email"``).
        lang: Target language; region tags and unknown codes fall back to
            English.

    Returns:
        The localized label, or the raw ``term`` when no translation exists.
    """
    if not term:
        return ""
    table = _LOCALIZED.get(kind, {})
    entry = table.get(term)
    if entry is None:
        return term
    language = normalize_language(lang)
    return entry.get(language) or entry.get("en") or term


def localize_channel(channel: str | None, lang: str | None = "en") -> str:
    """Localize a delivery-channel term. See :func:`localize`."""
    return localize("channel", channel, lang)


def localize_read_status(status: str | None, lang: str | None = "en") -> str:
    """Localize a read-status term (``read`` / ``unread``). See :func:`localize`."""
    return localize("read_status", status, lang)


def localize_dispatch_status(status: str | None, lang: str | None = "en") -> str:
    """Localize a dispatch-outcome term. See :func:`localize`."""
    return localize("dispatch_status", status, lang)


# ── Normalizers ───────────────────────────────────────────────────────────


def normalize_channel(value: Any) -> str:
    """Map an arbitrary value to a known channel or :data:`UNKNOWN`.

    Case-insensitive and whitespace-tolerant so callers can pass values that
    came straight off a request without pre-cleaning them.
    """
    if not isinstance(value, str):
        return UNKNOWN
    candidate = value.strip().lower()
    return candidate if candidate in CHANNELS else UNKNOWN


def read_status_of(is_read: Any) -> str:
    """Return ``"read"`` or ``"unread"`` for a truthy/falsy read flag."""
    return "read" if bool(is_read) else "unread"


# ── Rate results ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RateResult:
    """A single rate together with the components that produced it.

    Every field is present so a UI can render the rate, a progress bar and a
    tooltip without recomputing anything, and so the derivation is auditable.

    Attributes:
        numerator: The counted-in part (delivered, or read).
        denominator: The base the rate is measured against (sent, or delivered).
        rate: The ratio in the closed range [0.0, 1.0].
        percent: The same ratio as a percentage in [0.0, 100.0].
        defined: ``False`` when the denominator was zero (nothing to measure),
            in which case ``rate`` and ``percent`` are reported as zero.
        explainer: One plain-language sentence describing the derivation.
    """

    numerator: int
    denominator: int
    rate: float
    percent: float
    defined: bool
    explainer: str


def _require_count(value: int, label: str) -> int:
    """Validate that ``value`` is a non-negative integer count.

    Booleans are rejected explicitly: they are technically ``int`` but a
    ``True`` slipping in as a count is almost always a caller bug.

    Raises:
        ValueError: If ``value`` is not an integer or is negative.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        msg = f"{label} must be an integer count, got {value!r}"
        raise ValueError(msg)
    if value < 0:
        msg = f"{label} must not be negative, got {value}"
        raise ValueError(msg)
    return value


def _ratio(numerator: int, denominator: int) -> tuple[float, float]:
    """Return ``(rate, percent)`` clamped into [0, 1] and [0, 100]."""
    rate = numerator / denominator
    rate = min(1.0, max(0.0, rate))
    return round(rate, 6), round(rate * 100.0, 4)


def delivery_rate(sent: int, delivered: int) -> RateResult:
    """Share of sent notifications that reached their channel.

    Derived as ``delivered / sent``. When nothing was sent the rate is
    undefined; rather than raise or return ``NaN`` this reports a defined,
    zero-valued result flagged with ``defined=False`` so the caller can show
    "no data yet" instead of a misleading 0%.

    Args:
        sent: How many notifications were handed to a channel. Non-negative.
        delivered: How many of those were accepted by the channel. Non-negative
            and never greater than ``sent``.

    Returns:
        A :class:`RateResult` with ``rate`` in [0, 1] and ``percent`` in
        [0, 100].

    Raises:
        ValueError: If either count is negative or not an integer, or if
            ``delivered`` exceeds ``sent`` (an impossible measurement).
    """
    _require_count(sent, "sent")
    _require_count(delivered, "delivered")
    if delivered > sent:
        msg = f"delivered ({delivered}) cannot exceed sent ({sent})"
        raise ValueError(msg)

    if sent == 0:
        return RateResult(
            numerator=0,
            denominator=0,
            rate=0.0,
            percent=0.0,
            defined=False,
            explainer="Nothing was sent yet, so the delivery rate is not defined; shown as 0%.",
        )

    rate, percent = _ratio(delivered, sent)
    explainer = (
        f"Delivery rate is delivered / sent: {delivered} of {sent} "
        f"notifications reached their channel ({_pct_text(percent)})."
    )
    return RateResult(
        numerator=delivered,
        denominator=sent,
        rate=rate,
        percent=percent,
        defined=True,
        explainer=explainer,
    )


def read_rate(delivered: int, read: int) -> RateResult:
    """Share of delivered notifications that were opened.

    Derived as ``read / delivered``. When nothing was delivered the rate is
    undefined and reported as a defined, zero-valued result with
    ``defined=False``.

    Args:
        delivered: How many notifications reached the user. Non-negative.
        read: How many of those were opened. Non-negative and never greater
            than ``delivered``.

    Returns:
        A :class:`RateResult` with ``rate`` in [0, 1] and ``percent`` in
        [0, 100].

    Raises:
        ValueError: If either count is negative or not an integer, or if
            ``read`` exceeds ``delivered``.
    """
    _require_count(delivered, "delivered")
    _require_count(read, "read")
    if read > delivered:
        msg = f"read ({read}) cannot exceed delivered ({delivered})"
        raise ValueError(msg)

    if delivered == 0:
        return RateResult(
            numerator=0,
            denominator=0,
            rate=0.0,
            percent=0.0,
            defined=False,
            explainer="Nothing was delivered yet, so the read rate is not defined; shown as 0%.",
        )

    rate, percent = _ratio(read, delivered)
    explainer = (
        f"Read rate is read / delivered: {read} of {delivered} "
        f"delivered notifications were opened ({_pct_text(percent)})."
    )
    return RateResult(
        numerator=read,
        denominator=delivered,
        rate=rate,
        percent=percent,
        defined=True,
        explainer=explainer,
    )


def _pct_text(percent: float) -> str:
    """Format a percentage as plain text, dropping a redundant ``.0`` tail."""
    if percent == int(percent):
        return f"{int(percent)}%"
    return f"{percent:.2f}%"


# ── Counts and unread ─────────────────────────────────────────────────────


def _extract(item: Any, attr: str, key: Callable[[Any], Any] | None) -> Any:
    """Pull a field off an item that may be a scalar, mapping or object.

    A caller-supplied ``key`` wins; otherwise a mapping is indexed by ``attr``
    and any other object is read by attribute. Scalars pass through untouched
    so an iterable of plain channel strings or read flags just works.
    """
    if key is not None:
        return key(item)
    if isinstance(item, Mapping):
        return item.get(attr)
    if isinstance(item, (str, bool, int)):
        return item
    return getattr(item, attr, None)


def count_by_channel(items: Iterable[Any], *, key: Callable[[Any], Any] | None = None) -> dict[str, int]:
    """Count items per delivery channel.

    Every known channel is present in the result (zero when unused) so a UI
    can render a stable set of bars. An ``"unknown"`` bucket is added only if
    at least one item did not map to a known channel.

    Args:
        items: Channel strings, mappings with a ``channel`` field, or objects
            with a ``channel`` attribute.
        key: Optional accessor returning the channel value for each item.

    Returns:
        A dict of channel to count. Never raises on odd input; unrecognised
        values land in ``"unknown"``.
    """
    counts: dict[str, int] = dict.fromkeys(CHANNELS, 0)
    unknown = 0
    for item in items:
        channel = normalize_channel(_extract(item, "channel", key))
        if channel == UNKNOWN:
            unknown += 1
        else:
            counts[channel] += 1
    if unknown:
        counts[UNKNOWN] = unknown
    return counts


def count_by_status(items: Iterable[Any], *, key: Callable[[Any], Any] | None = None) -> dict[str, int]:
    """Count items by read status (``read`` / ``unread``).

    Both keys are always present so the caller can index the result without
    guarding for a missing bucket.

    Args:
        items: Read flags, mappings with an ``is_read`` field, or objects with
            an ``is_read`` attribute.
        key: Optional accessor returning the read flag for each item.

    Returns:
        A dict with ``"read"`` and ``"unread"`` counts.
    """
    counts: dict[str, int] = dict.fromkeys(READ_STATUSES, 0)
    for item in items:
        counts[read_status_of(_extract(item, "is_read", key))] += 1
    return counts


def unread_count(items: Iterable[Any], *, key: Callable[[Any], Any] | None = None) -> int:
    """Count how many items are unread. See :func:`count_by_status`."""
    return count_by_status(items, key=key)["unread"]


def unread_from_totals(total: int, read: int) -> int:
    """Compute unread from aggregate totals with full guards.

    Complements :func:`unread_count` for callers that already hold summary
    numbers (for example a paginated total plus a read count) rather than the
    individual rows.

    Args:
        total: Total notifications. Non-negative.
        read: Notifications already read. Non-negative and not greater than
            ``total``.

    Returns:
        ``total - read``, always in the range ``[0, total]``.

    Raises:
        ValueError: If either count is negative or not an integer, or if
            ``read`` exceeds ``total``.
    """
    _require_count(total, "total")
    _require_count(read, "read")
    if read > total:
        msg = f"read ({read}) cannot exceed total ({total})"
        raise ValueError(msg)
    return total - read


def explain_unread(total: int, read: int) -> str:
    """Return one plain-language sentence explaining the unread count.

    Raises:
        ValueError: Propagated from :func:`unread_from_totals` on bad input.
    """
    unread = unread_from_totals(total, read)
    return f"Unread is total - read: {unread} of {total} notifications are not yet read."


# ── Timestamps (ISO 8601, UTC) ────────────────────────────────────────────


def to_iso8601(moment: datetime) -> str:
    """Render a datetime as an ISO 8601 string in UTC.

    A naive datetime is assumed to be UTC; an aware one is converted to UTC.
    This keeps timestamps locale-independent and directly sortable.

    Args:
        moment: The datetime to render.

    Returns:
        An ISO 8601 string such as ``"2026-07-05T12:30:00+00:00"``.

    Raises:
        ValueError: If ``moment`` is not a ``datetime``.
    """
    if not isinstance(moment, datetime):
        msg = f"moment must be a datetime, got {type(moment).__name__}"
        raise ValueError(msg)
    aware = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    return aware.isoformat()


def now_iso8601() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


# ── Composite summary ─────────────────────────────────────────────────────


def engagement_summary(
    sent: int,
    delivered: int,
    read: int,
    *,
    lang: str | None = "en",
    at: datetime | None = None,
) -> dict[str, Any]:
    """Bundle delivery and read rates with their explainers and a timestamp.

    A single call a dashboard can render straight through: the two rates carry
    their own components and one-line explainers, and the read-status counts
    come with localized labels so the same payload reads correctly in English,
    German or Russian.

    Args:
        sent: Notifications handed to a channel.
        delivered: Notifications accepted by a channel (``<= sent``).
        read: Delivered notifications that were opened (``<= delivered``).
        lang: Language for the status labels; English fallback otherwise.
        at: Timestamp for the snapshot; defaults to now.

    Returns:
        A JSON-serialisable dict with ``delivery``, ``read``, ``counts``,
        ``labels`` and an ISO 8601 ``generated_at``.

    Raises:
        ValueError: Propagated from the rate helpers on impossible inputs.
    """
    delivery = delivery_rate(sent, delivered)
    reading = read_rate(delivered, read)
    unread = delivered - read
    counts = {"read": read, "unread": unread}
    labels = {status: localize_read_status(status, lang) for status in READ_STATUSES}
    generated_at = to_iso8601(at) if at is not None else now_iso8601()
    return {
        "delivery": {
            "numerator": delivery.numerator,
            "denominator": delivery.denominator,
            "rate": delivery.rate,
            "percent": delivery.percent,
            "defined": delivery.defined,
            "explainer": delivery.explainer,
        },
        "read": {
            "numerator": reading.numerator,
            "denominator": reading.denominator,
            "rate": reading.rate,
            "percent": reading.percent,
            "defined": reading.defined,
            "explainer": reading.explainer,
        },
        "counts": counts,
        "labels": labels,
        "generated_at": generated_at,
    }
