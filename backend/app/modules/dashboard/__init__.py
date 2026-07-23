# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Dashboard rollup module - single endpoint that returns all dashboard
widget payloads in one round-trip, eliminating the per-project fan-out
the frontend used to do (N requests for N projects per widget).

Module name: ``oe_dashboard`` (singular) - distinct from ``oe_dashboards``
(plural, analytical Parquet/DuckDB dashboards). Mounted at
``/api/v1/dashboard/`` by the module loader.
"""
