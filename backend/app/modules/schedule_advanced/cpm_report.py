# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Claims-grade schedule-quality report assembly.

A thin, pure aggregation layer on top of :mod:`app.modules.schedule_advanced.cpm`.
It runs one CPM pass and projects it through the claims-grade post-processors
(Longest Path, float-path decomposition, scheduling QA log, criticality
selection, and the generated explain strings), returning a single plain-``dict``
report that the API layer can hand straight to a Pydantic response model.

Kept deliberately free of any FastAPI / ORM imports so it imports and runs under
plain CPython (no app.database / PEP 695 barrier) and is unit-testable in
isolation. The ORM-to-network glue lives in the router; everything numeric and
forensic lives here or in :mod:`cpm`.
"""

from __future__ import annotations

from typing import Any

from app.modules.schedule_advanced.cpm import (
    QAOptions,
    TaskNetwork,
    compute_cpm,
    es_ef_durations,
    float_explanation,
    longest_path,
    multiple_float_paths,
    scheduling_qa_log,
    select_critical,
    why_critical,
)


def quality_report(network: TaskNetwork, *, options: QAOptions | None = None) -> dict[str, Any]:
    """Assemble the full claims-grade quality report for ``network``.

    Runs ``compute_cpm`` once and derives every claims-grade view from that
    single pass so the numbers are internally consistent. Activity ids are
    stringified so the result is JSON / Pydantic friendly regardless of whether
    the network was built from UUID rows or short string codes.

    The returned dict's keys line up 1:1 with ``ScheduleQualityResponse`` (minus
    ``schedule_id``, which the caller supplies), so the router can splat it
    directly into the response model.
    """
    results = compute_cpm(network)
    es, ef, durations = es_ef_durations(network, results)

    lp = longest_path(network, results, durations, es, ef)
    fpaths = multiple_float_paths(network, results, durations, es, ef)
    qa = scheduling_qa_log(network, results, options)
    critical = select_critical(results, "total_float")

    project_finish = max(ef.values()) if ef else 0

    # Explain strings for the driving (longest) path - the chain a reviewer
    # reads first. Generated strictly from the computed numbers + driving edge.
    explanations = [
        {
            "activity_id": str(aid),
            "why_critical": why_critical(network, results, durations, es, ef, aid),
            "float_explanation": float_explanation(network, results, durations, es, ef, aid),
        }
        for aid in lp
    ]

    return {
        "project_finish_workday": int(project_finish),
        "num_activities": len(results),
        "num_critical": len(critical),
        "longest_path": [str(aid) for aid in lp],
        "longest_path_length_days": sum(durations.get(aid, 0) for aid in lp),
        "critical_activity_ids": sorted(str(aid) for aid in critical),
        "float_paths": [
            {
                "index": p.index,
                "activity_ids": [str(aid) for aid in p.activity_ids],
                "length_days": p.length_days,
                "relative_float": p.relative_float,
            }
            for p in fpaths
        ],
        "qa_log": [
            {
                "code": f.code,
                "severity": f.severity,
                "activity_id": str(f.activity_id),
                "message": f.message,
            }
            for f in qa
        ],
        "explanations": explanations,
    }
