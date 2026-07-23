"""OpenConstructionERP - Mexico partner pack.

Pre-configures OCERP for Mexican construction: the APU unit-price method
(analisis de precios unitarios) under the LOPSRM public-works law and its
reglamento, IVA 16 percent with the 8 percent border region and IVA/ISR
retenciones, CFDI 4.0 invoicing, social-housing bodies (INFONAVIT, FOVISSSTE,
CONAVI), IMSS and NOM-031-STPS site safety, 32 states and MXN.

This package exports a module-level ``MANIFEST`` instance referenced from
``pyproject.toml``::

    [project.entry-points."openconstructionerp.packs"]
    mexico-mx = "openconstructionerp_mexico_mx:MANIFEST"

The OCERP core discovers this entry point at boot, validates the manifest,
and applies the pack overrides (branding, locale, cost regions, methodology,
validation rule packs, onboarding script).

This pack is written from public Mexican standards, laws and tax rules.
"""

from __future__ import annotations

from .manifest import MANIFEST

__all__ = ["MANIFEST"]
__version__ = "0.1.0"
