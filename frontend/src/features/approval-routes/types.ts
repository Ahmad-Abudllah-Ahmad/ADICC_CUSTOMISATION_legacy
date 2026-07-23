// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Wire types for Approval Routes (Wave 2, Epic A).
//
// Mirrors backend/app/modules/approval_routes/schemas.py — keep in sync.
// A *Route* is a reusable workflow template (steps with approver role/user
// + decision mode + optional SLA). An *Instance* is a running workflow on
// a specific target (markup, submittal, RFI, …).
//
// IMPORTANT: every field below maps 1:1 to a Pydantic response model on
// the backend. The instance row is flat — it carries `step_states` (one
// decision row per approver per step), NOT an expanded per-step ladder.
// The UI joins `step_states` against the route's `steps` (fetched via
// getRoute) to render the ladder, and derives the active step from
// `current_step_ordinal` (1-based).

/** Decision mode for a step — how many approvers must approve before it
 *  closes. ``all`` = every distinct approver who acted (role steps degrade
 *  to "any" — see backend note), ``any`` = first one wins, ``majority`` =
 *  > 50 % of approvers who acted. */
export type RouteStepMode = 'all' | 'any' | 'majority';

/** Lifecycle status of a running instance. Mirrors
 *  models.INSTANCE_STATUSES — there is no separate "in_progress" state;
 *  ``pending`` IS the active state. */
export type InstanceStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';

/** Per-step decision recorded in a StepState row. Mirrors
 *  models.STEP_DECISIONS. */
export type StepDecisionState = 'pending' | 'approved' | 'rejected';

/** Outcome a user submits via the decide endpoint — exactly what the
 *  backend DecisionSubmit.decision Literal accepts. */
export type StepDecision = 'approved' | 'rejected';

/** A template step — pinned to a role OR a specific user (mutually
 *  exclusive). One of the two must be set. ``ordinal`` is 1-based and
 *  dense (1, 2, 3, …). */
export interface RouteStep {
  id: string;
  route_id: string;
  ordinal: number;
  approver_role: string | null;
  approver_user_id: string | null;
  mode: RouteStepMode;
  sla_hours: number | null;
}

/** A reusable approval-route template scoped to a project (or global). */
export interface ApprovalRoute {
  id: string;
  project_id: string | null;
  target_kind: string;
  name: string;
  is_active: boolean;
  steps: RouteStep[];
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** Payload shape when creating/updating a step inside a route. ``ordinal``
 *  is 1-based and required on create (the backend enforces dense ordinals). */
export interface RouteStepPayload {
  ordinal: number;
  approver_role?: string | null;
  approver_user_id?: string | null;
  mode: RouteStepMode;
  sla_hours?: number | null;
}

export interface ApprovalRouteCreatePayload {
  project_id?: string | null;
  target_kind: string;
  name: string;
  is_active?: boolean;
  steps: RouteStepPayload[];
}

/** Patch payload. ``steps`` is optional — when supplied the whole step
 *  list is replaced server-side (delete + reinsert). target_kind and
 *  project_id are immutable on the backend and are not part of the patch. */
export interface ApprovalRouteUpdatePayload {
  name?: string;
  is_active?: boolean;
  steps?: RouteStepPayload[];
}

/** One per-approver decision row inside a running instance. Mirrors
 *  StepStateResponse. ``decision`` is one of pending/approved/rejected. */
export interface StepState {
  id: string;
  instance_id: string;
  step_id: string;
  approver_user_id: string | null;
  decision: StepDecisionState;
  comment: string | null;
  decided_at: string | null;
  created_at: string;
}

/** A running approval workflow on a specific target. Flat shape — the
 *  ladder is reconstructed by the UI from the route's steps + these
 *  step_states. */
export interface ApprovalInstance {
  id: string;
  route_id: string;
  target_kind: string;
  target_id: string;
  current_step_ordinal: number;
  status: InstanceStatus;
  started_at: string;
  completed_at: string | null;
  started_by: string | null;
  /** Who must act on the current step right now (the "ball in court").
   *  null means the step's own approver / role (or its resolved
   *  out-of-office delegate) is responsible; a value is a one-tap
   *  reassignment override pinned via the reassign endpoint. */
  current_assignee_user_id?: string | null;
  created_at: string;
  updated_at: string;
  step_states: StepState[];
}

export interface InstanceCreatePayload {
  route_id: string;
  target_kind: string;
  target_id: string;
}

export interface InstanceDecidePayload {
  step_id: string;
  decision: StepDecision;
  comment?: string | null;
}

export interface InstanceCancelPayload {
  reason?: string | null;
}

/** One-tap reassignment of an instance's current step to another user.
 *  Mirrors the backend ReassignInstance schema. */
export interface InstanceReassignPayload {
  to_user_id: string;
  reason?: string | null;
}

/** Metadata payload from GET /approval-routes/meta — single source of
 *  truth for the validated whitelists so the UI never drifts from the DB. */
export interface ApprovalRoutesMeta {
  target_kinds: string[];
  step_modes: RouteStepMode[];
  instance_statuses: InstanceStatus[];
}

/* ── Delegations (out-of-office) ──────────────────────────────────── */

/** A read-side out-of-office hand-off row. Mirrors the backend
 *  DelegationResponse. The ``delegator`` is the user who handed their
 *  approvals away; the ``delegate`` is the stand-in who covers them. An
 *  optional ``starts_at``/``ends_at`` window scopes when it is live; a
 *  null ``project_id`` is a blanket hand-off across every project. */
export interface ApprovalDelegation {
  id: string;
  delegator_user_id: string;
  delegate_user_id: string;
  project_id: string | null;
  starts_at: string | null;
  ends_at: string | null;
  is_active: boolean;
  reason: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** Create payload for an out-of-office hand-off. The delegator is always
 *  the authenticated caller server-side — never sent in the body. Mirrors
 *  the backend DelegationCreate. Datetimes are ISO-8601 strings. */
export interface DelegationCreatePayload {
  delegate_user_id: string;
  project_id?: string | null;
  starts_at?: string | null;
  ends_at?: string | null;
  reason?: string | null;
}

/** Which side of a hand-off to list: ``mine`` = hand-offs the caller
 *  created (approvals they delegated away); ``covering`` = hand-offs
 *  naming the caller as the stand-in. */
export type DelegationRole = 'mine' | 'covering';

/** Escalation standing of one instance's current step (#17). Mirrors the
 *  backend EscalationOut. ``has_sla`` is false when there is no live SLA
 *  clock; ``severity`` is the overrun band, ``next_target`` the approver to
 *  escalate to now (or null), and ``level`` the 1-based escalation level. */
export type EscalationSeverity = 'on_time' | 'late' | 'breached' | 'critical';

export interface Escalation {
  instance_id: string;
  target_kind: string;
  current_step_ordinal: number;
  has_sla: boolean;
  severity: EscalationSeverity;
  hours_overdue: number;
  should_escalate: boolean;
  next_target: string | null;
  level: number;
  reason: string;
  chain_length: number;
  current_holder: string | null;
}
