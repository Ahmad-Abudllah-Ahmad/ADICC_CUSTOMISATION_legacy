# Architecture Decision Records

This directory holds ADRs — short, timestamped records of non-obvious
architectural choices. Each file answers three questions:

1. **Context.** What problem forced the decision?
2. **Decision.** What we picked, and (briefly) why.
3. **Consequences.** What changes, what we now can't easily undo,
   and what the rollback path is.

## Index

| ID | Status | Title | Date |
|---|---|---|---|
| [001](001-snapshot-storage-model.md) | Accepted | Snapshot storage model (SQL meta + Parquet data + DuckDB queries) | 2026-04-23 |
| [002](002-no-ifcopenshell-ddc-canonical-only.md) | Accepted | No IfcOpenShell — DDC canonical format is the single source of truth | 2026-04-25 |
| [003](003-vector-match-service.md) | Accepted | Vector match service | — |
| [2026-05-28](2026-05-28-partner-pack-architecture.md) | Accepted | Partner-pack architecture (Shape A, single-tenant, entry-points) | 2026-05-28 |

## Writing a new ADR

- Filename: `NNN-kebab-case-title.md`, ID monotonic.
- Status: `Proposed` → `Accepted` → `Superseded by NNN` (never delete).
- Keep it short. One page is a feature, not a bug.
- Link to the files that implement the decision once they exist.
