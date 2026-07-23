# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""BIM-LV container module (DIN SPEC 91350).

Reads and writes the BIM-LV container that bundles a GAEB LV, a reference to
the IFC/BIM model and the position-to-element link table, and materializes the
container's links onto existing BOQ positions and BIM elements.
"""
