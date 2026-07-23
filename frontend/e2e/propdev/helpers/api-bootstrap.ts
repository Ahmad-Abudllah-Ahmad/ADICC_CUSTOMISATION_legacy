/**
 * API-level helpers to seed property_dev fixtures without going through
 * the UI. Each scenario calls ``bootstrapDevelopmentGraph(...)`` to land
 * with a Development + Phase + Block + HouseType + Plot graph ready,
 * then drives the specific journey via the same helper functions.
 *
 * Why API-first?
 *   - The happy-path spec captures 30+ screenshots; doing every entity
 *     CRUD through the UI would push runtime past 5 minutes per worker.
 *   - We need deterministic state for the FSM / IDOR specs. Driving
 *     them via UI introduces a layer of optimistic-update flakiness.
 *
 * The helpers all return the JSON body so callers can chain by id.
 */
import { type APIRequestContext, expect } from '@playwright/test';

/** UUID v4 stub-free type alias for ergonomics. */
export type UUID = string;

export interface DevelopmentGraph {
  project_id: UUID;
  development_id: UUID;
  phase_id: UUID;
  block_id: UUID;
  house_type_id: UUID;
  variant_id: UUID;
  plot_id: UUID;
}

/**
 * Unique-suffix helper. Property_dev `code` fields are unique per parent
 * — re-using the same code across runs trips a 409. We seed everything
 * with a per-run random suffix so the suite is re-runnable without
 * needing a fresh DB.
 */
export function uniqueSuffix(): string {
  return Math.random().toString(36).slice(2, 8);
}

async function jsonOk<T>(
  api: APIRequestContext,
  method: 'GET' | 'POST' | 'PATCH' | 'DELETE',
  url: string,
  body?: unknown,
): Promise<T> {
  const res = await api.fetch(url, {
    method,
    data: body as Record<string, unknown> | undefined,
    failOnStatusCode: false,
  });
  if (!res.ok()) {
    throw new Error(
      `[propdev-bootstrap] ${method} ${url} -> ${res.status()}: ${await res.text()}`,
    );
  }
  // 204 returns no body.
  if (res.status() === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

/** GET ``/projects/`` and return the first id, creating one if empty. */
export async function ensureProject(api: APIRequestContext): Promise<UUID> {
  const projects = await jsonOk<Array<{ id: UUID }>>(api, 'GET', '/api/v1/projects/');
  if (projects.length > 0) return projects[0]!.id;
  const created = await jsonOk<{ id: UUID }>(api, 'POST', '/api/v1/projects/', {
    name: `R6 PropDev E2E ${uniqueSuffix()}`,
    description: 'Auto-created for R6 property_dev E2E suite',
    currency: 'EUR',
  });
  return created.id;
}

/**
 * Build the full Development → Phase → Block → HouseType → Variant → Plot
 * spine ready for a Lead → Reservation → SPA happy path.
 */
export async function bootstrapDevelopmentGraph(
  api: APIRequestContext,
  opts: { name?: string; currency?: string; jurisdiction?: string } = {},
): Promise<DevelopmentGraph> {
  const suffix = uniqueSuffix();
  const currency = opts.currency ?? 'EUR';
  const project_id = await ensureProject(api);

  const dev = await jsonOk<{ id: UUID }>(api, 'POST', '/api/v1/property-dev/developments/', {
    project_id,
    code: `R6-DEV-${suffix}`,
    name: opts.name ?? `R6 Garden Towers ${suffix}`,
    location_address: 'Berlin, Germany',
    total_plots: 12,
    sales_phase: 'sales',
    launch_date: '2026-01-01',
    completion_date: '2027-12-31',
    status: 'active',
    units: 'metric',
    metadata: { jurisdiction: opts.jurisdiction ?? 'rera_dubai' },
  });

  const phase = await jsonOk<{ id: UUID }>(api, 'POST', '/api/v1/property-dev/phases/', {
    development_id: dev.id,
    code: `PH-${suffix}`,
    name: 'Phase 1 — Ground Floor',
    sequence: 1,
    planned_start: '2026-01-15',
    planned_end: '2026-06-30',
    status: 'under_construction',
  });

  const block = await jsonOk<{ id: UUID }>(api, 'POST', '/api/v1/property-dev/blocks/', {
    phase_id: phase.id,
    code: `BL-${suffix}`,
    name: 'Block A',
    levels_count: 5,
    units_per_level: 4,
    orientation: 'SE',
    status: 'under_construction',
  });

  const houseType = await jsonOk<{ id: UUID }>(api, 'POST', '/api/v1/property-dev/house-types/', {
    development_id: dev.id,
    code: `HT-${suffix}`,
    name: 'Type Aria',
    bedrooms: 3,
    bathrooms: 2,
    total_area_m2: 124.5,
    footprint_m2: 64,
    levels: 2,
    base_price: 540000,
    currency,
  });

  const variant = await jsonOk<{ id: UUID }>(
    api,
    'POST',
    '/api/v1/property-dev/house-type-variants/',
    {
      house_type_id: houseType.id,
      code: `VAR-${suffix}`,
      name: 'Premium finish',
      modifier_pct: 5,
    },
  );

  const plot = await jsonOk<{ id: UUID }>(api, 'POST', '/api/v1/property-dev/plots/', {
    development_id: dev.id,
    plot_number: `P-${suffix}`,
    house_type_id: houseType.id,
    house_type_variant_id: variant.id,
    block_id: block.id,
    level_in_block: 3,
    position_on_floor: 'A',
    orientation: 'SE',
    area_m2: 124.5,
    price_base: 540000,
    currency,
    status: 'ready',
  });

  return {
    project_id,
    development_id: dev.id,
    phase_id: phase.id,
    block_id: block.id,
    house_type_id: houseType.id,
    variant_id: variant.id,
    plot_id: plot.id,
  };
}

/** Create a Lead at the top of the funnel. */
export async function createLead(
  api: APIRequestContext,
  development_id: UUID,
  overrides: Record<string, unknown> = {},
): Promise<{ id: UUID; status: string; nurture_stage: string | null }> {
  return jsonOk(api, 'POST', '/api/v1/property-dev/leads/', {
    development_id,
    source: 'web_form',
    lead_score: 70,
    full_name: 'R6 Test Buyer',
    email: `r6-buyer-${uniqueSuffix()}@example.com`,
    phone: '+49 30 12345678',
    language: 'en',
    currency: 'EUR',
    budget_min: 400000,
    budget_max: 600000,
    notes: 'Strong interest, viewed model unit',
    ...overrides,
  });
}

/** Convert a Lead → Reservation (creates Buyer shadow row by default). */
export async function convertLeadToReservation(
  api: APIRequestContext,
  lead_id: UUID,
  plot_id: UUID,
  opts: {
    deposit?: number;
    currency?: string;
    cooling_off_days?: number;
    expires_at?: string;
  } = {},
): Promise<{ id: UUID; status: string; cooling_off_until: string | null }> {
  return jsonOk(api, 'POST', `/api/v1/property-dev/leads/${lead_id}/convert-to-reservation`, {
    plot_id,
    deposit_amount: opts.deposit ?? 25000,
    currency: opts.currency ?? 'EUR',
    cooling_off_days: opts.cooling_off_days ?? 7,
    expires_at: opts.expires_at,
    create_buyer: true,
  });
}

/** Convert a Reservation → SPA (draft). */
export async function convertReservationToSpa(
  api: APIRequestContext,
  reservation_id: UUID,
  opts: { totalValue?: number; currency?: string; signingDate?: string } = {},
): Promise<{ id: UUID; status: string }> {
  return jsonOk(api, 'POST', `/api/v1/property-dev/reservations/${reservation_id}/convert-to-spa`, {
    signing_date: opts.signingDate ?? '2026-06-01',
    total_value: opts.totalValue ?? 540000,
    currency: opts.currency ?? 'EUR',
    governing_law: 'DE-BE',
    language: 'en',
    terms_version: 'v1.0',
  });
}

/** Add a buyer as ContractParty. */
export async function addContractParty(
  api: APIRequestContext,
  sales_contract_id: UUID,
  buyer_id: UUID,
  ownership_pct: number,
  party_role: 'primary' | 'co_buyer' | 'guarantor' = 'co_buyer',
): Promise<{ id: UUID; ownership_pct: string }> {
  return jsonOk(api, 'POST', '/api/v1/property-dev/contract-parties/', {
    sales_contract_id,
    buyer_id,
    ownership_pct,
    party_role,
  });
}

/**
 * Create a Buyer row directly (bypassing the Lead funnel) — used when a
 * scenario needs additional ContractParty entries.
 */
export async function createBuyer(
  api: APIRequestContext,
  development_id: UUID,
  overrides: Record<string, unknown> = {},
): Promise<{ id: UUID }> {
  return jsonOk(api, 'POST', '/api/v1/property-dev/buyers/', {
    development_id,
    full_name: `R6 Co-buyer ${uniqueSuffix()}`,
    email: `r6-co-${uniqueSuffix()}@example.com`,
    phone: '+49 30 98765432',
    language: 'en',
    status: 'lead',
    currency: 'EUR',
    ...overrides,
  });
}

/** Activate a draft SPA: send-for-signature → sign (counter-sign). */
export async function activateSpa(
  api: APIRequestContext,
  spa_id: UUID,
): Promise<{ id: UUID; status: string }> {
  await jsonOk(api, 'POST', `/api/v1/property-dev/sales-contracts/${spa_id}/send-for-signature`, {
    e_sign_envelope_id: `e2e-envelope-${uniqueSuffix()}`,
  });
  return jsonOk(api, 'POST', `/api/v1/property-dev/sales-contracts/${spa_id}/sign`, {
    signing_date: '2026-06-02',
  });
}

/** Create a 5-milestone payment schedule + instalments and activate it. */
export async function createPaymentScheduleWithInstalments(
  api: APIRequestContext,
  spa_id: UUID,
  total: number,
  currency = 'EUR',
): Promise<{ schedule_id: UUID; instalment_ids: UUID[] }> {
  const schedule = await jsonOk<{ id: UUID }>(
    api,
    'POST',
    '/api/v1/property-dev/payment-schedules/',
    {
      sales_contract_id: spa_id,
      currency,
      total_amount: total,
      late_fee_pct: 1.5,
      grace_period_days: 5,
    },
  );
  const milestones = [
    { event: 'spa_signed', label: '10% on signing', pct: 10 },
    { event: 'foundation_complete', label: '20% on foundation', pct: 20 },
    { event: 'structural_complete', label: '30% on structure', pct: 30 },
    { event: 'finishes_complete', label: '30% on finishes', pct: 30 },
    { event: 'handover', label: '10% on handover', pct: 10 },
  ];
  const instalment_ids: UUID[] = [];
  for (let i = 0; i < milestones.length; i += 1) {
    const m = milestones[i]!;
    const ins = await jsonOk<{ id: UUID }>(api, 'POST', '/api/v1/property-dev/instalments/', {
      schedule_id: schedule.id,
      sequence: i + 1,
      milestone_label: m.label,
      milestone_event: m.event,
      due_date: `2026-${String(7 + i).padStart(2, '0')}-15`,
      amount: (total * m.pct) / 100,
    });
    instalment_ids.push(ins.id);
  }
  await jsonOk(api, 'POST', `/api/v1/property-dev/payment-schedules/${schedule.id}/activate`);
  return { schedule_id: schedule.id, instalment_ids };
}

/** Mark an instalment paid (records the payment + may credit escrow). */
export async function markInstalmentPaid(
  api: APIRequestContext,
  instalment_id: UUID,
  amount: number,
): Promise<{ status: string }> {
  return jsonOk(api, 'POST', `/api/v1/property-dev/instalments/${instalment_id}/mark-paid`, {
    amount,
    paid_at: new Date().toISOString(),
    invoice_ref: `INV-${uniqueSuffix()}`,
  });
}

/** Create a handover row for a plot. */
export async function createHandover(
  api: APIRequestContext,
  plot_id: UUID,
  scheduled_at = '2027-11-15',
): Promise<{ id: UUID }> {
  return jsonOk(api, 'POST', '/api/v1/property-dev/handovers/', {
    plot_id,
    scheduled_at,
    notes: 'R6 E2E scheduled handover',
  });
}

/** Add a Snag to a handover. */
export async function createSnag(
  api: APIRequestContext,
  handover_id: UUID,
  description: string,
  severity: 'cosmetic' | 'minor' | 'major' | 'safety' = 'minor',
): Promise<{ id: UUID }> {
  return jsonOk(api, 'POST', '/api/v1/property-dev/snags/', {
    handover_id,
    description,
    severity,
    location_in_plot: 'Living room',
  });
}

/** Mark a snag fixed. */
export async function fixSnag(api: APIRequestContext, snag_id: UUID): Promise<void> {
  await jsonOk(api, 'POST', `/api/v1/property-dev/snags/${snag_id}/fix`);
}

/** Complete handover (final-check + keys). */
export async function completeHandover(
  api: APIRequestContext,
  handover_id: UUID,
): Promise<{ id: UUID; final_check_passed: boolean }> {
  return jsonOk(api, 'POST', `/api/v1/property-dev/handovers/${handover_id}/complete`, {
    completed_at: '2027-12-01',
    customer_signature_ref: `sig-${uniqueSuffix()}`,
    keys_handed_over_at: '2027-12-01',
    final_check_passed: true,
    snag_count_at_handover: 0,
  });
}

/** Raise + close a warranty claim. */
export async function raiseWarrantyClaim(
  api: APIRequestContext,
  plot_id: UUID,
  buyer_id: UUID,
  description = 'R6 E2E warranty claim — kitchen tap drip',
): Promise<{ id: UUID }> {
  return jsonOk(api, 'POST', '/api/v1/property-dev/warranty-claims/', {
    plot_id,
    buyer_id,
    description,
    category: 'defect',
    raised_at: '2028-01-15',
  });
}

/** Fully drain a development graph — used for teardown after each spec. */
export async function teardownDevelopment(
  api: APIRequestContext,
  development_id: UUID,
): Promise<void> {
  // The backend cascades most child rows on Development delete, but
  // unattached entities (loose Brokers, Leads) stay alive. We try the
  // top-level delete; if it 409s we still want to continue cleanly.
  await api
    .delete(`/api/v1/property-dev/developments/${development_id}`)
    .catch(() => undefined);
}

/** Asserts an HTTP status was returned by an endpoint call. */
export async function expectStatus(
  api: APIRequestContext,
  url: string,
  expected: number,
  init: {
    method?: 'GET' | 'POST' | 'PATCH' | 'DELETE';
    body?: unknown;
  } = {},
): Promise<void> {
  const res = await api.fetch(url, {
    method: init.method ?? 'GET',
    data: init.body as Record<string, unknown> | undefined,
    failOnStatusCode: false,
  });
  if (res.status() !== expected) {
    const text = await res.text();
    expect(res.status(), `${init.method ?? 'GET'} ${url} expected ${expected}, got ${res.status()}: ${text}`).toBe(
      expected,
    );
  }
}
