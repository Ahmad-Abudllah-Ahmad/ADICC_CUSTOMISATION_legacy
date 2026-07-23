# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Unified cross-collection semantic search module.

Exposes a single ``GET /api/v1/search/`` endpoint that fans out to every
registered vector collection (BOQ, documents, tasks, risks, BIM elements,
…) and merges the results via Reciprocal Rank Fusion.
"""
