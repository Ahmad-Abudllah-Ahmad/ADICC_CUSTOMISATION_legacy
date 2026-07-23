# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Match Elements module.

Maps elements from BIM/CAD/PDF/photo sources to CWICR cost positions
through interactive group-based matching with multiple matcher methods
(vector + lexical, with LLM rerank planned). The result lands in a
project's BOQ as positions with auto-loaded resource decomposition,
each resource quantity scaled by the group total quantity.

Phase A: BIM source only. DWG/PDF/photo adapters land in later phases
behind the same SourceAdapter interface.
"""
