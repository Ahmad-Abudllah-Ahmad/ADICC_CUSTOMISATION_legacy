// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * API helpers for the Interface Management module.
 *
 * Multi-package / multi-contractor coordination: the per-project register of
 * interfaces (the handshakes where one party's work meets another's), the
 * actions needed to close each one, and the derived register rollup and
 * per-work-package health view.
 *
 * Every endpoint is project-scoped in the PATH and mounted under
 * ``/v1/interface-management/projects/{projectId}/...``.
 */

import { apiGet, apiPost, apiPatch, apiDelete } from '@/shared/lib/api';

/* -- Vocabularies ---------------------------------------------------------- */

export type InterfaceType =
  | 'physical'
  | 'functional'
  | 'contractual'
  | 'spatial'
  | 'information'
  | 'schedule';

export type InterfaceStatus =
  | 'identified'
  | 'open'
  | 'in_progress'
  | 'agreed'
  | 'closed'
  | 'disputed'
  | 'on_hold';

export type InterfacePriority = 'low' | 'medium' | 'high' | 'critical';

export type ActionStatus = 'open' | 'done' | 'cancelled';

export const ALL_INTERFACE_TYPES: InterfaceType[] = [
  'physical',
  'functional',
  'contractual',
  'spatial',
  'information',
  'schedule',
];

export const ALL_INTERFACE_STATUSES: InterfaceStatus[] = [
  'identified',
  'open',
  'in_progress',
  'agreed',
  'closed',
  'disputed',
  'on_hold',
];

export const ALL_PRIORITIES: InterfacePriority[] = ['low', 'medium', 'high', 'critical'];

/** Statuses whose handshake is settled, so the interface is no longer overdue. */
const SETTLED_STATUSES: ReadonlySet<InterfaceStatus> = new Set(['agreed', 'closed']);
/** Statuses exempt from the overdue check (settled or deliberately paused). */
const OVERDUE_EXEMPT_STATUSES: ReadonlySet<string> = new Set(['agreed', 'closed', 'on_hold']);

/** The synthetic bucket label the backend uses for interfaces with no work package. */
export const UNASSIGNED = 'unassigned';

/* -- Types ----------------------------------------------------------------- */

export interface InterfaceRecord {
  id: string;
  project_id: string;
  reference: string;
  title: string;
  description: string | null;
  owner_party: string | null;
  owner_subcontractor_id: string | null;
  accepter_party: string | null;
  accepter_subcontractor_id: string | null;
  discipline_from: string | null;
  discipline_to: string | null;
  work_package_from: string | null;
  work_package_to: string | null;
  interface_type: string | null;
  status: string;
  priority: string | null;
  need_by_date: string | null;
  agreed_date: string | null;
  closed_date: string | null;
  rfi_id: string | null;
  schedule_activity_id: string | null;
  location: string | null;
  sort_order: number;
  notes: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface InterfaceAction {
  id: string;
  project_id: string;
  interface_id: string;
  description: string;
  action_party: string | null;
  due_date: string | null;
  status: string;
  completed_date: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

/** A lightweight reference to an interface, used in overdue / disputed lists. */
export interface InterfaceRef {
  interface_id: string | null;
  reference: string;
  title: string;
  status: string;
  priority: string | null;
  interface_type: string | null;
  owner_party: string | null;
  accepter_party: string | null;
  work_package_from: string | null;
  need_by_date: string | null;
  agreed_date: string | null;
  open_action_count: number;
}

/** Health rollup for one originating work package. */
export interface WorkPackageHealth {
  work_package: string;
  total: number;
  open: number;
  overdue: number;
  agreed: number;
  /** Percentage as a decimal string, or ``null`` for an empty group. */
  health_score: string | null;
}

/** Per-work-package health summary plus the overdue and disputed lists. */
export interface WorkPackageHealthReport {
  project_id: string;
  as_of: string;
  total: number;
  is_healthy: boolean;
  work_packages: WorkPackageHealth[];
  overdue: InterfaceRef[];
  disputed: InterfaceRef[];
}

/** The full interface register rollup for a project. */
export interface InterfaceRegister {
  project_id: string;
  as_of: string;
  total: number;
  per_status: Record<string, number>;
  per_priority: Record<string, number>;
  per_type: Record<string, number>;
  agreed_pct: string | null;
  overall_health_score: string | null;
  total_open_actions: number;
  is_healthy: boolean;
  overdue: InterfaceRef[];
  disputed: InterfaceRef[];
  work_packages: WorkPackageHealth[];
}

/* -- Write payloads -------------------------------------------------------- */

export interface InterfaceWritePayload {
  reference: string;
  title: string;
  description?: string | null;
  owner_party?: string | null;
  accepter_party?: string | null;
  discipline_from?: string | null;
  discipline_to?: string | null;
  work_package_from?: string | null;
  work_package_to?: string | null;
  interface_type?: InterfaceType | null;
  status?: InterfaceStatus;
  priority?: InterfacePriority | null;
  need_by_date?: string | null;
  location?: string | null;
  notes?: string | null;
}

export interface ActionWritePayload {
  description: string;
  action_party?: string | null;
  due_date?: string | null;
  status?: ActionStatus;
  completed_date?: string | null;
}

export interface InterfaceFilters {
  status?: InterfaceStatus | '';
  work_package?: string | '';
  interface_type?: InterfaceType | '';
  priority?: InterfacePriority | '';
}

/* -- Helpers --------------------------------------------------------------- */

/** Parse a percentage decimal string (``"66.67"`` / ``null``) to a number or ``null``. */
export function parsePct(value: string | null | undefined): number | null {
  if (value == null) return null;
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : null;
}

/**
 * True when an interface is past its need-by date and not yet settled or paused.
 * Mirrors the backend ``is_overdue`` rule so highlighted rows match the register.
 */
export function isInterfaceOverdue(
  iface: Pick<InterfaceRecord, 'need_by_date' | 'status'>,
  today: string,
): boolean {
  if (!iface.need_by_date) return false;
  if (OVERDUE_EXEMPT_STATUSES.has(iface.status)) return false;
  return iface.need_by_date < today;
}

/** True when the interface handshake is settled (agreed or closed). */
export function isInterfaceSettled(status: string): boolean {
  return SETTLED_STATUSES.has(status as InterfaceStatus);
}

const BASE = '/v1/interface-management/projects';

/* -- Interfaces ------------------------------------------------------------ */

export async function fetchInterfaces(
  projectId: string,
  filters?: InterfaceFilters,
): Promise<InterfaceRecord[]> {
  const params = new URLSearchParams();
  if (filters?.status) params.set('status', filters.status);
  if (filters?.work_package) params.set('work_package', filters.work_package);
  if (filters?.interface_type) params.set('interface_type', filters.interface_type);
  if (filters?.priority) params.set('priority', filters.priority);
  const qs = params.toString();
  return apiGet<InterfaceRecord[]>(`${BASE}/${projectId}/interfaces${qs ? `?${qs}` : ''}`);
}

export async function createInterface(
  projectId: string,
  payload: InterfaceWritePayload,
): Promise<InterfaceRecord> {
  return apiPost<InterfaceRecord, InterfaceWritePayload>(
    `${BASE}/${projectId}/interfaces`,
    payload,
  );
}

export async function updateInterface(
  projectId: string,
  interfaceId: string,
  payload: Partial<InterfaceWritePayload>,
): Promise<InterfaceRecord> {
  return apiPatch<InterfaceRecord, Partial<InterfaceWritePayload>>(
    `${BASE}/${projectId}/interfaces/${interfaceId}`,
    payload,
  );
}

export async function deleteInterface(projectId: string, interfaceId: string): Promise<void> {
  await apiDelete<void>(`${BASE}/${projectId}/interfaces/${interfaceId}`);
}

/* -- Actions --------------------------------------------------------------- */

export async function fetchActions(
  projectId: string,
  opts?: { interface_id?: string; status?: ActionStatus },
): Promise<InterfaceAction[]> {
  const params = new URLSearchParams();
  if (opts?.interface_id) params.set('interface_id', opts.interface_id);
  if (opts?.status) params.set('status', opts.status);
  const qs = params.toString();
  return apiGet<InterfaceAction[]>(`${BASE}/${projectId}/actions${qs ? `?${qs}` : ''}`);
}

export async function createAction(
  projectId: string,
  interfaceId: string,
  payload: ActionWritePayload,
): Promise<InterfaceAction> {
  return apiPost<InterfaceAction, ActionWritePayload>(
    `${BASE}/${projectId}/interfaces/${interfaceId}/actions`,
    payload,
  );
}

export async function updateAction(
  projectId: string,
  actionId: string,
  payload: Partial<ActionWritePayload>,
): Promise<InterfaceAction> {
  return apiPatch<InterfaceAction, Partial<ActionWritePayload>>(
    `${BASE}/${projectId}/actions/${actionId}`,
    payload,
  );
}

/* -- Derived register views ------------------------------------------------ */

export async function fetchWorkPackageHealth(
  projectId: string,
): Promise<WorkPackageHealthReport> {
  return apiGet<WorkPackageHealthReport>(`${BASE}/${projectId}/work-package-health`);
}

export async function fetchRegister(projectId: string): Promise<InterfaceRegister> {
  return apiGet<InterfaceRegister>(`${BASE}/${projectId}/register`);
}
