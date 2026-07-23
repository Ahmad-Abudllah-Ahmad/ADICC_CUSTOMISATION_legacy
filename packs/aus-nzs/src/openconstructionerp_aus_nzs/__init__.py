"""DEPRECATED — ``openconstructionerp-aus-nzs`` meta-pack.

This combined Australia + New Zealand pack has been **split** into two
single-jurisdiction packs because AU and NZ have different default
currencies (AUD vs NZD), different GST rates (10 % vs 15 %) and
substantially different contract / building-code regimes that should not
share a single ``default_currency`` or ``default_tax_template``:

* ``openconstructionerp-aus`` — Australia (AUD, 10 % GST, NCC 2022,
  AS 1684/3600/4100, AS 4000-1997 / AS 4902-2000, Rawlinsons AU 2024).
* ``openconstructionerp-nzs`` — New Zealand (NZD, 15 % GST, NZBC,
  NZS 3604:2011, NZS 3910:2023, Rawlinsons NZ).

For backward compatibility this shim re-exports the **Australia** pack
manifest (AU is the larger market) and emits a ``DeprecationWarning`` at
import time. Users explicitly pinning ``aus-nzs`` will keep working but
should migrate to one of the per-country packs.

The shim's entry point is still ``aus-nzs`` so any existing
``OE_PARTNER_PACK=aus-nzs`` deployment continues to resolve, but the
loaded manifest's ``slug`` will be ``aus``.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "openconstructionerp-aus-nzs is deprecated; install "
    "openconstructionerp-aus (AUD, 10% GST) or openconstructionerp-nzs "
    "(NZD, 15% GST) instead. This shim now re-exports the Australia pack.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export the Australia manifest as the default.
# If openconstructionerp-aus is not installed this import will raise
# ImportError, which is the correct failure mode — the deprecated meta
# pack pulls openconstructionerp-aus as a hard dependency in pyproject.
from openconstructionerp_aus import MANIFEST  # noqa: E402

__all__ = ["MANIFEST"]
__version__ = "0.2.0"
