// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * Unified approvals/alerts inbox - API client + wire types.
 *
 * Mirrors the backend ``GET /api/v1/dashboard/inbox/`` payload
 * (``app/modules/dashboard/schemas.py::InboxResponse``). The endpoint
 * aggregates the caller's pending approvals (file-approval steps +
 * change-order approval steps) and their unread in-app notifications, scoped
 * IDOR-safely to accessible projects. We READ existing per-module data - this
 * client introduces no new store.
 */
import { apiGet } from '@/shared/lib/api';

export type InboxKind = 'approval' | 'alert';
export type InboxSeverity = 'info' | 'warning' | 'critical';

/** One actionable row in the unified inbox. */
export interface InboxItem {
  /** Stable per-source id, e.g. ``notification:<uuid>``. */
  id: string;
  kind: InboxKind;
  /** Module of origin, e.g. ``file_approval`` / ``change_order`` / ``notification``. */
  source: string;
  /** Resolved English text OR an i18n key (see ``title_key``). */
  title: string | null;
  /** i18n key the frontend renders with ``body_context`` when present. */
  title_key?: string | null;
  /** i18n key for the secondary body line (alert notifications). */
  body_key?: string | null;
  body_context?: Record<string, unknown>;
  project_id?: string | null;
  project_name?: string | null;
  entity_type?: string | null;
  entity_id?: string | null;
  /** Relative app route the row links to. */
  action_url?: string | null;
  severity: InboxSeverity;
  /** ISO-8601; drives the newest-first sort. */
  created_at?: string | null;
}

export interface InboxResponse {
  items: InboxItem[];
  /** Scoped count across both streams (pre-cap). */
  total: number;
  /** Scoped pending-approval count. */
  approvals_count: number;
  /** Scoped alert count. */
  alerts_count: number;
  generated_at: string;
}

/**
 * Fetch the unified inbox for the signed-in user.
 *
 * @param limit Maximum rows in the returned list (1-200). Counts are pre-cap.
 */
export function fetchInbox(limit = 50): Promise<InboxResponse> {
  const params = new URLSearchParams({ limit: String(limit) });
  return apiGet<InboxResponse>(`/v1/dashboard/inbox/?${params.toString()}`);
}
