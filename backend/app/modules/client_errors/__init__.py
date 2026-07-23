# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Client-side error sink module.

Receives anonymised error reports from the React frontend's
``errorLogger.ts``. The endpoint is intentionally write-only and
storage-free in v4.2.x - payloads are logged at WARNING level via the
standard logger so they show up alongside backend errors in the existing
log aggregation pipeline. Persistent storage (a ``client_error_events``
table + retention sweep) is a v4.3 follow-up.

Hardened by an in-memory per-IP rate limiter at 30 req/min so a runaway
client (or a hostile script pointed at the public endpoint) cannot flood
the log pipeline.
"""
