"""OpenConstructionERP — Australia partner pack.

Pre-configures OCERP for Australian general contractors against the
National Construction Code (NCC) 2022, AS 1684 timber-framing series
(Parts 1-4), AS 3600 concrete, AS 4100 steel, AS 4000-1997 / AS 4902-2000
contract suite and Rawlinsons Australian Construction Handbook 2024.

This package exports a module-level ``MANIFEST`` instance referenced
from ``pyproject.toml``::

    [project.entry-points."openconstructionerp.partner_packs"]
    aus = "openconstructionerp_aus:MANIFEST"

The OCERP core discovers this entry point at boot, validates the
manifest, and applies the partner overrides (branding, locale,
cost regions, validation rule packs, onboarding script).
"""

from __future__ import annotations

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
__version__ = "0.1.0"
