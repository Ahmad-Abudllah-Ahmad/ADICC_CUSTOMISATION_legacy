# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Formwork module - temporary mould catalogue + per-BOQ assignments.

Three core entities:

* :class:`FormworkSystem` - catalogue of physical formwork systems
  (Doka / PERI / MEVA / plywood / etc.) with material, supplier,
  reuses_max and per-m2 unit rate.
* :class:`FormworkAssignment` - links a project (and optionally a BOQ
  position) to a system with an area, an expected reuse count and a
  waste percentage. Server recomputes ``computed_unit_cost`` and
  ``computed_total`` on every create / update so the BOQ rollup sees
  reuse-aware figures, not the raw catalogue rate.
* :class:`FormworkScheduleLine` - optional pour-by-pour breakdown
  under an assignment (cycle planning for climbing systems / large
  slabs); list-only for the MVP.
"""
