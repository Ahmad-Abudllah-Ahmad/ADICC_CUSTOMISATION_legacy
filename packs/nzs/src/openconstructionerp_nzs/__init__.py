"""OpenConstructionERP — New Zealand partner pack.

Pre-configures OCERP for New Zealand contractors against the New Zealand
Building Code (NZBC) acceptable solutions, NZS 3604:2011 timber-framed
buildings, NZS 3910:2023 Conditions of Contract for Building and Civil
Engineering Construction, MBIE compliance documents and Rawlinsons NZ
Construction Handbook.

The OCERP core discovers this entry point at boot, validates the
manifest, and applies the partner overrides.
"""

from __future__ import annotations

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
__version__ = "0.1.0"
