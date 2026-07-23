/**
 * Scenario #5 — Multi-buyer ContractParty constraints.
 *
 * The service enforces:
 *   - ownership_pct sum across parties ≤ 100 (422 on overflow)
 *   - changes only permitted in draft / sent_for_signature
 *   - one Buyer can only be a party once per SPA (409 on duplicate)
 *
 * We seed an SPA, add 3 parties (40/30/30), try to add a 4th @ 5% (must
 * 422 because 105 > 100), update one to 20%, then delete one and assert
 * the sum constraint after each mutation.
 */
import { expect, test } from '@playwright/test';
import {
  addContractParty,
  bootstrapDevelopmentGraph,
  convertLeadToReservation,
  convertReservationToSpa,
  createBuyer,
  createLead,
  teardownDevelopment,
} from './helpers/api-bootstrap';
import { demoLogin } from './helpers/auth';
import { Shooter } from './helpers/screenshots';

test.describe.configure({ mode: 'serial' });

test('multi-buyer ContractParty enforces ownership sum ≤ 100', async () => {
  const shooter = new Shooter('multi_buyer');
  const admin = await demoLogin('admin');
  const graph = await bootstrapDevelopmentGraph(admin.api, {
    name: 'R6 Multi-Buyer Dev',
  });
  const lead = await createLead(admin.api, graph.development_id);
  const reservation = await convertLeadToReservation(admin.api, lead.id, graph.plot_id);
  const spa = await convertReservationToSpa(admin.api, reservation.id);

  // The lead-convert flow may auto-create a primary party. Listen + clean.
  const listRes0 = await admin.api.get(
    `/api/v1/property-dev/contract-parties/?sales_contract_id=${spa.id}`,
  );
  const initial = (await listRes0.json()) as Array<{ id: string; ownership_pct: string }>;
  for (const p of initial) {
    await admin.api.delete(`/api/v1/property-dev/contract-parties/${p.id}`);
  }

  // Now build 3 fresh buyers + add parties at 40/30/30.
  const buyerA = await createBuyer(admin.api, graph.development_id, {
    full_name: 'Alex Buyer',
  });
  const buyerB = await createBuyer(admin.api, graph.development_id, {
    full_name: 'Bella Buyer',
  });
  const buyerC = await createBuyer(admin.api, graph.development_id, {
    full_name: 'Cyril Buyer',
  });
  const buyerD = await createBuyer(admin.api, graph.development_id, {
    full_name: 'Dana Overflow',
  });

  const partyA = await addContractParty(admin.api, spa.id, buyerA.id, 40, 'primary');
  const partyB = await addContractParty(admin.api, spa.id, buyerB.id, 30, 'co_buyer');
  const partyC = await addContractParty(admin.api, spa.id, buyerC.id, 30, 'co_buyer');
  shooter.saveJson('three_parties_40_30_30', { partyA, partyB, partyC });

  // 4th party @ 5% → would push sum to 105 → must 422.
  const overflowRes = await admin.api.post('/api/v1/property-dev/contract-parties/', {
    data: {
      sales_contract_id: spa.id,
      buyer_id: buyerD.id,
      ownership_pct: 5,
      party_role: 'co_buyer',
    },
  });
  expect(overflowRes.status()).toBe(422);
  shooter.saveJson('overflow_4th_party_422', {
    status: overflowRes.status(),
    body: await overflowRes.text(),
  });

  // Update partyA from 40 → 20 (frees 20 points).
  const updateA = await admin.api.patch(
    `/api/v1/property-dev/contract-parties/${partyA.id}`,
    { data: { ownership_pct: 20 } },
  );
  expect(updateA.ok()).toBeTruthy();
  shooter.saveJson('partyA_reduced_to_20', await updateA.json());

  // Now the 4th party should fit at 20 (sum = 20+30+30+20 = 100).
  const acceptRes = await admin.api.post('/api/v1/property-dev/contract-parties/', {
    data: {
      sales_contract_id: spa.id,
      buyer_id: buyerD.id,
      ownership_pct: 20,
      party_role: 'co_buyer',
    },
  });
  expect(acceptRes.ok()).toBeTruthy();
  shooter.saveJson('4th_party_accepted_at_100', await acceptRes.json());

  // Delete partyC → sum becomes 70, list returns 3 rows.
  const delRes = await admin.api.delete(
    `/api/v1/property-dev/contract-parties/${partyC.id}`,
  );
  expect(delRes.ok()).toBeTruthy();
  const final = await admin.api.get(
    `/api/v1/property-dev/contract-parties/?sales_contract_id=${spa.id}`,
  );
  const finalRows = (await final.json()) as Array<{ ownership_pct: string }>;
  expect(finalRows.length).toBe(3);
  const sum = finalRows.reduce((acc, r) => acc + Number(r.ownership_pct), 0);
  expect(sum).toBe(70);
  shooter.saveJson('after_delete_partyC', { rows: finalRows, sum });

  // Duplicate-buyer: try to add buyerA again — must 409.
  const dupRes = await admin.api.post('/api/v1/property-dev/contract-parties/', {
    data: {
      sales_contract_id: spa.id,
      buyer_id: buyerA.id,
      ownership_pct: 5,
      party_role: 'co_buyer',
    },
  });
  expect(dupRes.status()).toBe(409);
  shooter.saveJson('duplicate_buyer_409', { status: dupRes.status() });

  await teardownDevelopment(admin.api, graph.development_id);
});
