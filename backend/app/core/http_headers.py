# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""HTTP header helpers.

Centralises the one piece of header construction that is easy to get wrong:
``Content-Disposition`` for file downloads. HTTP header values must be Latin-1
encodable, but file/model/report names routinely contain non-Latin-1 characters
(Cyrillic, CJK, accented Latin, em-dashes, emoji). Interpolating such a name
straight into ``filename="..."`` makes the ASGI server raise UnicodeEncodeError
while serialising the response headers, surfacing as an opaque HTTP 500.

``content_disposition_attachment`` emits the RFC 6266 form: an ASCII-sanitised
``filename=`` fallback for legacy clients plus a ``filename*=UTF-8''<pct>``
parameter that modern browsers prefer, so the original name survives intact and
the download never 500s.
"""

from urllib.parse import quote

__all__ = ["content_disposition_attachment"]


def content_disposition_attachment(filename: str, *, inline: bool = False) -> str:
    """Build a safe ``Content-Disposition`` header value for a download.

    Args:
        filename: The desired (possibly non-ASCII) file name.
        inline: Use ``inline`` instead of ``attachment`` as the disposition type.

    Returns:
        A header value safe to place in a Latin-1 HTTP header, e.g.
        ``attachment; filename="COBie_?????.xlsx"; filename*=UTF-8''COBie_%D0%9C...xlsx``
    """
    disp = "inline" if inline else "attachment"
    # ASCII fallback: replace anything non-ASCII with '?', and strip the two
    # characters that would break the quoted-string syntax.
    ascii_fallback = filename.encode("ascii", "replace").decode("ascii").replace('"', "").replace("\\", "")
    # RFC 5987 / 6266: percent-encode the UTF-8 bytes for the filename* form.
    encoded = quote(filename, safe="")
    return f"{disp}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"
