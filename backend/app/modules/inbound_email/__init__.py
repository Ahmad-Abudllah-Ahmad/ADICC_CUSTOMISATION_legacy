# DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Inbound email module.

Turns project correspondence that arrives as a stored message file into
structured data the platform can act on. The intake is file-based: an operator
imports a saved RFC-822 message (an exported ".eml" file or equivalent raw
bytes), not a live mailbox connection. Two dependency-free engines do the work.

The parser (``eml_parser``) reads a raw message with the standard library and
returns a normalized record: the header essentials (subject, sender, recipients,
copy list, date), the threading identifiers that let later steps stitch a
conversation together (message id, in-reply-to, references), the best available
text body (preferring the plain-text part and falling back to tag-stripped
markup), and lightweight attachment metadata. It is best-effort and never raises
on malformed input.

The delay detector (``delay_detection``) scans that free text for language that
commonly signals a construction delay event - adverse weather, blocked site
access, late information, design changes and variations, resource shortages,
outstanding statutory approvals, and unforeseen ground conditions - and proposes
a small starter set of schedule activities (a fragnet) to feed a forensic-delay
workflow. It uses plain keyword and regular-expression matching with bounded
confidence scoring; there is no model and no network call.

Both engines are stdlib-only so they unit-test on the local runner without the
database or web framework. The module loader discovers and mounts the ``router``
submodule at ``/api/v1/inbound-email`` and calls :func:`on_startup` once at
boot; this ``__init__`` does not import the router at top level so the engines
stay independently importable.
"""

__all__ = ["on_startup"]


async def on_startup() -> None:
    """Module startup hook - register the module's permissions."""
    from app.modules.inbound_email.permissions import (
        register_inbound_email_permissions,
    )

    register_inbound_email_permissions()
