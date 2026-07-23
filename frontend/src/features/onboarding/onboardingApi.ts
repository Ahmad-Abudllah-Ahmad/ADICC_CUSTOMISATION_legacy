// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Thin client for the onboarding provisioning API (backend module
// `oe_onboarding`, mounted at /api/v1/onboarding). The wizard uses this to push
// the heavy first-run work - importing a regional cost base, installing a
// sample project - to the server as background jobs and then poll their live
// state, instead of awaiting the raw imports inline and blocking the user.

import { apiPost } from '@/shared/lib/api';

/** One background provisioning job's live state, as returned by the server. */
export interface OnboardingJobState {
  id: string;
  /** e.g. 'onboarding.load_cwicr' | 'onboarding.install_demo'. */
  kind: string;
  /** The item being provisioned (region id or demo id), when known. */
  arg: string | null;
  /** pending | started | success | failed | cancelled. */
  state: string;
  /** 0..100 progress reported by the handler. */
  pct: number;
  /** Latest human progress message, when the handler set one. */
  message: string | null;
  /** Error message when the job failed. */
  error: string | null;
}

/** What to provision in the background. Mirrors the backend `ProvisionRequest`. */
export interface ProvisionOnboardingBody {
  region?: string | null;
  demo_ids?: string[];
}

interface JobsEnvelope {
  jobs: OnboardingJobState[];
}

/**
 * Kick off the heavy first-run work as background jobs. Returns the job states
 * (with ids) so the caller can poll {@link fetchOnboardingStatus}. Idempotent
 * on the server per user and item, so a retried call reuses the running job.
 */
export async function provisionOnboarding(
  body: ProvisionOnboardingBody,
): Promise<OnboardingJobState[]> {
  const res = await apiPost<JobsEnvelope, ProvisionOnboardingBody>(
    '/v1/onboarding/provision',
    body,
  );
  return res.jobs ?? [];
}

/**
 * Poll the live state of previously provisioned jobs by id. The server returns
 * only jobs owned by the caller, so ids from another user are silently dropped.
 */
export async function fetchOnboardingStatus(ids: string[]): Promise<OnboardingJobState[]> {
  if (ids.length === 0) return [];
  const res = await apiPost<JobsEnvelope, { ids: string[] }>('/v1/onboarding/status', {
    ids,
  });
  return res.jobs ?? [];
}
