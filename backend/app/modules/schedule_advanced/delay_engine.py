# DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
# Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
"""Pure-Python forensic delay-analysis engine (T2.2).

Forensic delay analysis in the industry-standard suite is a manual,
expert-only exercise: the analyst hand-builds delay fragments ("fragnets"),
reschedules windows by hand and assembles exhibits in a spreadsheet. This
module turns the four standard methods into a deterministic, unit-testable
computation so a project-controls engineer (not only a claims consultant) can
produce a defensible analysis.

Like :mod:`cpm`, this module is intentionally self-contained: no SQLAlchemy,
no FastAPI, no third-party deps. Everything is plain ``dataclass`` + ``list`` /
``dict`` and it reuses the canonical CPM engine in :mod:`cpm` for every
reschedule. The persistence / API layer (service + router) loads activities,
calls these primitives and stores the windows + exhibit payload.

Every method compiles down to **one primitive**: take a set of activities,
splice in (or remove) a fragnet, run :func:`cpm.compute_cpm`, read the project
finish. Single source of correctness, single thing to test hardest.

Methods implemented:

    * **Time Impact Analysis (TIA)** - prospective. Insert a fragnet, reschedule,
      measure the forward push of project completion (float-absorbing).
    * **Windows / Watershed** - contemporaneous. Walk dated snapshots, measure the
      slip per window and attribute it by responsibility.
    * **As-Planned vs As-Built (APvAB)** - observational. Net slip between the
      as-planned baseline and the as-built record, attributed by event.
    * **Impacted As-Planned (IAP)** - modelled. Insert employer fragnets into the
      baseline net and measure the push.
    * **Collapsed As-Built (CAB)** - modelled. Remove employer fragnets from the
      as-built net and measure the recovery (the only caller using ``remove=True``).

Concurrency, pacing and mitigation are handled transparently in
:func:`attribute` (no black box): the analyst supplies responsibility +
concurrency/pacing flags; the engine attributes the gross slip under an explicit
apportionment method (Malmaison default, dominant-cause, time-but-for).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal

from .cpm import Activity, TaskNetwork, compute_cpm, critical_path

__all__ = [
    "ApportionmentMethod",
    "Attribution",
    "DelayEvent",
    "Fragnet",
    "IAPCABResult",
    "InsertMode",
    "Responsibility",
    "RewireOp",
    "TIAResult",
    "Window",
    "WindowsResult",
    "apply_fragnets",
    "attribute",
    "auto_fragnet",
    "project_finish",
    "run_apvab",
    "run_cab",
    "run_iap",
    "run_tia",
    "run_windows",
]

# ── Type aliases ─────────────────────────────────────────────────────────────

#: How a fragnet splices into the host network.
#:   * ``lengthen_activity`` - add days to the host activity's duration.
#:   * ``insert_after``      - insert new activity(ies) between the host and its
#:                             successors (the successors get re-pointed so the
#:                             inserted work actually pushes them).
#:   * ``insert_parallel``   - add new activity(ies) sharing the host's logic; the
#:                             host's successors gain the new node as an extra
#:                             predecessor so the longer of the two drives.
#:   * ``suspend_resume``    - a stop/start; modelled as idle days on the host
#:                             (same engine effect as ``lengthen_activity`` but
#:                             recorded distinctly for the narrative).
InsertMode = Literal["lengthen_activity", "insert_after", "insert_parallel", "suspend_resume"]

#: Party responsible for a delay event.
Responsibility = Literal["employer", "contractor", "neutral", "shared"]

#: Apportionment method when employer and contractor events run concurrently on
#: the critical path. ``malmaison`` (default) grants the employer the full EOT and
#: records the concurrency; ``dominant_cause`` awards the gross to whichever party
#: drove the longer span; ``time_but_for`` splits pro-rata by event span.
ApportionmentMethod = Literal["none", "dominant_cause", "time_but_for", "malmaison"]


# ── Fragnet / event data model (engine-side, plain) ──────────────────────────


@dataclass(frozen=True)
class RewireOp:
    """One edge redirection applied when a fragnet is spliced in.

    Attributes:
        successor_id: The activity whose predecessor logic changes.
        pred_id: The fragnet node the successor should now hang off.
        op: ``"redirect_from_host"`` replaces the successor's link to the host
            with a link to ``pred_id`` (insert-after semantics);
            ``"add"`` appends ``pred_id`` as an *extra* predecessor
            (insert-parallel semantics).
        dep_type: Link type to use for an ``"add"`` op (ignored by redirect,
            which preserves the original link type).
        lag: Lag for an ``"add"`` op.
    """

    successor_id: Any
    pred_id: Any
    op: Literal["redirect_from_host", "add"] = "redirect_from_host"
    dep_type: str = "FS"
    lag: int = 0


@dataclass(frozen=True)
class Fragnet:
    """A schedule fragment representing one event's network impact.

    ``new_activities`` are dicts in the exact :class:`cpm.Activity` shape
    (``id`` / ``duration`` / ``predecessors`` / ``required_resources``) so they
    deserialise with zero transform. ``rewires`` redirect or extend the host's
    successors so the inserted work actually drives the schedule. The recorded
    ``rewires`` also make removal exact, so Collapsed-As-Built is a true inverse
    of Impacted-As-Planned.
    """

    insert_mode: InsertMode
    host_id: Any
    added_duration_days: int = 0
    new_activities: tuple[dict[str, Any], ...] = ()
    rewires: tuple[RewireOp, ...] = ()


@dataclass(frozen=True)
class DelayEvent:
    """A discrete causative event with its network impact.

    Attributes:
        id: Stable event identifier.
        insert_at: The host activity the event drives - used to decide whether the
            event sits on the critical path during attribution.
        responsibility: Who carries the time risk.
        is_concurrent: Analyst-confirmed concurrency flag (informational; the
            engine derives concurrency from the critical path + overlap span).
        is_pacing: A pacing delay (a contractor pacing a pre-existing employer
            delay) - excluded from the *driving* set so it neither earns nor
            forfeits entitlement.
        event_start / event_end: Working-day window of the event (used to measure
            concurrency overlap). ``None`` means "unbounded / unknown".
        fragnets: The fragment(s) this event splices into the network.
    """

    id: Any
    insert_at: Any
    responsibility: Responsibility = "employer"
    is_concurrent: bool = False
    is_pacing: bool = False
    event_start: int | None = None
    event_end: int | None = None
    fragnets: tuple[Fragnet, ...] = ()


# ── Result data model ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TIAResult:
    """Outcome of a Time-Impact / Impacted-As-Planned reschedule."""

    baseline_finish: int
    impacted_finish: int
    entitlement_days: int
    critical_path_impact: bool
    drove_completion: bool
    newly_critical: tuple[Any, ...]
    baseline_critical: tuple[Any, ...]
    impacted_critical: tuple[Any, ...]


@dataclass(frozen=True)
class IAPCABResult:
    """Outcome of a modelled Impacted-As-Planned or Collapsed-As-Built run."""

    method: Literal["impacted_as_planned", "collapsed_as_built"]
    reference_finish: int
    modelled_finish: int
    entitlement_days: int


@dataclass(frozen=True)
class Attribution:
    """Responsibility split of a window's gross slip (working days).

    Invariant for a window without concurrency:
    ``gross == employer_days + contractor_days + neutral_days`` and
    ``concurrent_days == 0``. When employer and contractor events run
    concurrently on the critical path, ``concurrent_days`` records the overlap
    and the apportionment method decides who carries the entitling time
    (see :func:`attribute`).
    """

    employer_days: int
    contractor_days: int
    neutral_days: int
    concurrent_days: int

    @property
    def net_entitlement_days(self) -> int:
        """Extension-of-time entitlement = the employer-responsible time."""
        return self.employer_days


@dataclass(frozen=True)
class Window:
    """One analysis window in a Windows / Watershed run."""

    sequence_order: int
    finish_at_open: int
    finish_at_close: int
    gross_slip_days: int
    employer_days: int
    contractor_days: int
    neutral_days: int
    concurrent_days: int
    net_entitlement_days: int
    driving_event_ids: tuple[Any, ...]


@dataclass(frozen=True)
class WindowsResult:
    """Full Windows / Watershed outcome."""

    windows: tuple[Window, ...]
    total_entitlement_days: int
    total_gross_slip_days: int


# ── Core primitive: fragnet splicing ─────────────────────────────────────────


def _activity_from_dict(d: dict[str, Any]) -> Activity:
    """Deserialise an :class:`cpm.Activity` from a fragnet activity dict."""
    preds = [(t[0], t[1], int(t[2])) for t in d.get("predecessors", [])]
    return Activity(
        id=d["id"],
        duration=max(0, int(d.get("duration", 0))),
        predecessors=preds,
        required_resources=dict(d.get("required_resources", {})),
    )


def _apply_rewire(succ: Activity, host_id: Any, rw: RewireOp, *, remove: bool) -> Activity:
    """Return ``succ`` with one rewire op applied (or reverted when ``remove``)."""
    preds = list(succ.predecessors)
    if rw.op == "add":
        if remove:
            preds = [p for p in preds if p[0] != rw.pred_id]
        else:
            triple = (rw.pred_id, rw.dep_type, int(rw.lag))
            if triple not in preds:
                preds.append(triple)
    else:  # redirect_from_host
        rebuilt: list[tuple[Any, Any, int]] = []
        for pid, dep, lag in preds:
            if not remove and pid == host_id:
                rebuilt.append((rw.pred_id, dep, lag))
            elif remove and pid == rw.pred_id:
                rebuilt.append((host_id, dep, lag))
            else:
                rebuilt.append((pid, dep, lag))
        preds = rebuilt
    return replace(succ, predecessors=preds)


def apply_fragnets(
    base_activities: list[Activity],
    fragnets: list[Fragnet] | tuple[Fragnet, ...],
    *,
    remove: bool = False,
) -> TaskNetwork:
    """Splice ``fragnets`` into ``base_activities`` and return the new network.

    With ``remove=False`` the fragnets are inserted (TIA / IAP); with
    ``remove=True`` they are reverted (Collapsed-As-Built), which is an exact
    inverse because each fragnet records the duration delta, the inserted nodes
    and the edge redirections it made.

    Args:
        base_activities: The host network's activities (predecessors embedded).
        fragnets: Fragments to apply, in order.
        remove: Revert instead of apply.

    Returns:
        A fresh :class:`cpm.TaskNetwork`.
    """
    acts: dict[Any, Activity] = {a.id: a for a in base_activities}
    for f in fragnets:
        if f.insert_mode in ("lengthen_activity", "suspend_resume"):
            host = acts.get(f.host_id)
            if host is None:
                continue
            delta = -f.added_duration_days if remove else f.added_duration_days
            acts[host.id] = replace(host, duration=max(0, host.duration + delta))
        else:  # insert_after / insert_parallel
            if remove:
                for na in f.new_activities:
                    acts.pop(na["id"], None)
            else:
                for na in f.new_activities:
                    acts[na["id"]] = _activity_from_dict(na)
            for rw in f.rewires:
                succ = acts.get(rw.successor_id)
                if succ is None:
                    continue
                acts[succ.id] = _apply_rewire(succ, f.host_id, rw, remove=remove)
    return TaskNetwork(list(acts.values()))


def project_finish(network: TaskNetwork) -> int:
    """Project finish work-day = max early-finish across the network.

    Raises:
        cpm.CycleError: if the (possibly spliced) network contains a cycle.
    """
    res = compute_cpm(network)
    return max((r.ef for r in res.values()), default=0)


def auto_fragnet(
    network: TaskNetwork,
    host_id: Any,
    mode: InsertMode,
    added_days: int,
    *,
    event_id: str = "ev",
) -> Fragnet:
    """Synthesise a default fragnet from an event + insert target + delay length.

    This is the wizard helper: the analyst picks a host activity, a mode and a
    delay length and the engine builds the splice (lengthen, insert-after,
    insert-parallel or suspend/resume) - they tweak rather than hand-build.
    """
    added = max(0, int(added_days))
    if mode in ("lengthen_activity", "suspend_resume"):
        return Fragnet(insert_mode=mode, host_id=host_id, added_duration_days=added)

    frag_id = f"{host_id}__frag__{event_id}"
    if mode == "insert_after":
        new_act = {"id": frag_id, "duration": added, "predecessors": [(host_id, "FS", 0)]}
        rewires = tuple(
            RewireOp(successor_id=s_id, pred_id=frag_id, op="redirect_from_host", dep_type=dep, lag=lag)
            for s_id, dep, lag in network.successors(host_id)
        )
        return Fragnet(
            insert_mode="insert_after",
            host_id=host_id,
            added_duration_days=added,
            new_activities=(new_act,),
            rewires=rewires,
        )

    # insert_parallel: the new node shares the host's predecessors and the host's
    # successors gain it as an extra predecessor (whichever path is longer drives).
    new_act = {
        "id": frag_id,
        "duration": added,
        "predecessors": list(network.predecessors(host_id)),
    }
    rewires = tuple(
        RewireOp(successor_id=s_id, pred_id=frag_id, op="add", dep_type=dep, lag=lag)
        for s_id, dep, lag in network.successors(host_id)
    )
    return Fragnet(
        insert_mode="insert_parallel",
        host_id=host_id,
        added_duration_days=added,
        new_activities=(new_act,),
        rewires=rewires,
    )


# ── Concurrency / apportionment ──────────────────────────────────────────────


def _interval(events: list[DelayEvent]) -> tuple[int, int] | None:
    """Bounding work-day interval covering ``events`` (None if undated)."""
    starts = [e.event_start for e in events if e.event_start is not None]
    ends = [e.event_end for e in events if e.event_end is not None]
    if not starts or not ends:
        return None
    return (min(starts), max(ends))


def _overlap(a: tuple[int, int] | None, b: tuple[int, int] | None) -> int:
    """Overlap length (work days) of two intervals; 0 if either is None."""
    if a is None or b is None:
        return 0
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def _span(events: list[DelayEvent]) -> int:
    """Total covered span (work days) of an event group; 0 if undated."""
    iv = _interval(events)
    return 0 if iv is None else max(0, iv[1] - iv[0])


def attribute(
    gross_slip: int,
    events: list[DelayEvent],
    network: TaskNetwork,
    *,
    method: ApportionmentMethod = "malmaison",
) -> Attribution:
    """Attribute a window's gross slip to employer / contractor / neutral.

    The driving set is the events that sit on the critical path of ``network``
    and are not pacing. Concurrency is the employer/contractor overlap span on
    that driving set; the apportionment ``method`` decides who carries the
    entitling time.

    A negative ``gross_slip`` is mitigation/acceleration and is credited (as a
    negative day count) to whichever party drove the recovery.
    """
    crit = set(critical_path(network))
    driving = [e for e in events if (e.insert_at in crit) and not e.is_pacing]
    emp = [e for e in driving if e.responsibility == "employer"]
    con = [e for e in driving if e.responsibility == "contractor"]
    neu = [e for e in driving if e.responsibility in ("neutral", "shared")]

    if gross_slip < 0:
        # Mitigation / acceleration: credit the party that drove the recovery.
        if con:
            return Attribution(0, gross_slip, 0, 0)
        if emp:
            return Attribution(gross_slip, 0, 0, 0)
        return Attribution(0, 0, gross_slip, 0)

    if gross_slip == 0 or not driving:
        # No driving cause on the critical path: neutral by default.
        return Attribution(0, 0, gross_slip if gross_slip else 0, 0) if not driving else Attribution(0, 0, 0, 0)

    if emp and con:
        concurrent = min(gross_slip, _overlap(_interval(emp), _interval(con)))
        if method == "dominant_cause":
            if _span(emp) >= _span(con):
                return Attribution(gross_slip, 0, 0, concurrent)
            return Attribution(0, gross_slip, 0, concurrent)
        if method == "time_but_for":
            emp_span, con_span = _span(emp), _span(con)
            total = emp_span + con_span
            if total <= 0:
                emp_share = gross_slip // 2
            else:
                emp_share = round(gross_slip * emp_span / total)
            return Attribution(emp_share, gross_slip - emp_share, 0, concurrent)
        # malmaison (default): employer carries the full EOT, concurrency recorded.
        return Attribution(gross_slip, 0, 0, concurrent)

    # Single-party (or neutral-only) driving cause - no concurrency.
    if emp:
        return Attribution(gross_slip, 0, 0, 0)
    if con:
        return Attribution(0, gross_slip, 0, 0)
    return Attribution(0, 0, gross_slip, 0)


# ── Methods ──────────────────────────────────────────────────────────────────


def run_tia(base_activities: list[Activity], event: DelayEvent) -> TIAResult:
    """Time Impact Analysis: insert the event's fragnet and measure the push.

    Float absorbs part of the delay, so the entitlement can be less than the
    fragnet length. Generalises the legacy single-duration-bump helper to
    inserted activities and suspend/resume while keeping float-absorption.
    """
    net0 = TaskNetwork(list(base_activities))
    finish0 = project_finish(net0)
    crit0 = set(critical_path(net0))

    net1 = apply_fragnets(base_activities, event.fragnets)
    finish1 = project_finish(net1)
    crit1 = set(critical_path(net1))

    return TIAResult(
        baseline_finish=finish0,
        impacted_finish=finish1,
        entitlement_days=max(0, finish1 - finish0),
        critical_path_impact=event.insert_at in crit1,
        drove_completion=finish1 > finish0,
        newly_critical=tuple(sorted(crit1 - crit0, key=str)),
        baseline_critical=tuple(sorted(crit0, key=str)),
        impacted_critical=tuple(sorted(crit1, key=str)),
    )


def run_iap(baseline_activities: list[Activity], employer_fragnets: list[Fragnet]) -> IAPCABResult:
    """Impacted As-Planned: insert employer fragnets into the baseline net."""
    base_finish = project_finish(TaskNetwork(list(baseline_activities)))
    impacted = project_finish(apply_fragnets(baseline_activities, employer_fragnets))
    return IAPCABResult(
        method="impacted_as_planned",
        reference_finish=base_finish,
        modelled_finish=impacted,
        entitlement_days=max(0, impacted - base_finish),
    )


def run_cab(asbuilt_activities: list[Activity], employer_fragnets: list[Fragnet]) -> IAPCABResult:
    """Collapsed As-Built: remove employer fragnets from the as-built net.

    The only caller using ``remove=True``. Relies on the fragnet rows recording
    the original host/successor links so removal restores but-for logic, making
    CAB the exact inverse of IAP on the same fragnet set.
    """
    asbuilt_finish = project_finish(TaskNetwork(list(asbuilt_activities)))
    collapsed = project_finish(apply_fragnets(asbuilt_activities, employer_fragnets, remove=True))
    return IAPCABResult(
        method="collapsed_as_built",
        reference_finish=asbuilt_finish,
        modelled_finish=collapsed,
        entitlement_days=max(0, asbuilt_finish - collapsed),
    )


def run_apvab(
    baseline_activities: list[Activity],
    asbuilt_activities: list[Activity],
    events: list[DelayEvent],
    *,
    method: ApportionmentMethod = "malmaison",
) -> tuple[int, Attribution]:
    """As-Planned vs As-Built: net finish slip + attribution (no synthetic net).

    Observational and lowest engine risk - both networks are real (baseline and
    as-built), the slip is their finish difference and the events attribute it.

    Returns:
        ``(net_slip_days, attribution)``.
    """
    base_finish = project_finish(TaskNetwork(list(baseline_activities)))
    asbuilt_net = TaskNetwork(list(asbuilt_activities))
    asbuilt_finish = project_finish(asbuilt_net)
    net_slip = asbuilt_finish - base_finish
    attr = attribute(net_slip, events, asbuilt_net, method=method)
    return net_slip, attr


def run_windows(
    snapshots: list[list[Activity]],
    events: list[DelayEvent],
    *,
    method: ApportionmentMethod = "malmaison",
    window_bounds: list[tuple[int, int]] | None = None,
) -> WindowsResult:
    """Windows / Watershed: per-window finish movement attributed by responsibility.

    Walks ordered dated snapshots (each is the updated schedule at a data date).
    For each consecutive pair the gross slip is the finish movement between them;
    the events overlapping that window attribute it. Contemporaneous - it uses
    the *actual* updated schedules, not a synthetic reschedule.

    Args:
        snapshots: Ordered list of activity lists, one per data date.
        events: Delay events with ``event_start`` / ``event_end`` work-day windows.
        method: Apportionment method for concurrent critical events.
        window_bounds: Optional explicit ``(open_day, close_day)`` per window for
            event-overlap testing; defaults to ``(i, i+1)`` index bounds.

    Returns:
        A :class:`WindowsResult`.
    """
    windows: list[Window] = []
    total_entitlement = 0
    total_gross = 0
    for i in range(len(snapshots) - 1):
        f_open = project_finish(TaskNetwork(list(snapshots[i])))
        net_close = TaskNetwork(list(snapshots[i + 1]))
        f_close = project_finish(net_close)
        gross = f_close - f_open

        if window_bounds is not None and i < len(window_bounds):
            lo, hi = window_bounds[i]
        else:
            lo, hi = i, i + 1
        win_events = [e for e in events if _event_in_window(e, lo, hi)]

        attr = attribute(gross, win_events, net_close, method=method)
        windows.append(
            Window(
                sequence_order=i + 1,
                finish_at_open=f_open,
                finish_at_close=f_close,
                gross_slip_days=gross,
                employer_days=attr.employer_days,
                contractor_days=attr.contractor_days,
                neutral_days=attr.neutral_days,
                concurrent_days=attr.concurrent_days,
                net_entitlement_days=attr.net_entitlement_days,
                driving_event_ids=tuple(e.id for e in win_events),
            )
        )
        total_entitlement += attr.net_entitlement_days
        total_gross += gross
    return WindowsResult(
        windows=tuple(windows),
        total_entitlement_days=total_entitlement,
        total_gross_slip_days=total_gross,
    )


def _event_in_window(event: DelayEvent, lo: int, hi: int) -> bool:
    """Whether an event's work-day span overlaps ``[lo, hi)``.

    An undated event is treated as spanning every window (conservative: the
    analyst placed it in the analysis, so it is considered).
    """
    if event.event_start is None and event.event_end is None:
        return True
    start = event.event_start if event.event_start is not None else lo
    end = event.event_end if event.event_end is not None else hi
    return start < hi and end > lo
