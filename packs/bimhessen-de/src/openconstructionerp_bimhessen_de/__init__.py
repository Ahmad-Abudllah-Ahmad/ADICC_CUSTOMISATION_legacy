"""BIM-Cluster Hessen partner pack for OpenConstructionERP.

Pre-configures the platform for German BIM consultancies and
engineering offices: DIN 276, GAEB X83/X84/X86, VOB/A+B+C 2019,
ISO 19650 CDE, BKI Baukosten benchmarks, HOAI 2021 fee scale, and
a Leistungsverzeichnis-specific BOQ-quality rule set.
"""

from __future__ import annotations

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
__version__ = "0.2.0"
