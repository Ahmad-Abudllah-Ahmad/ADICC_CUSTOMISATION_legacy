// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for onTimeTileModel - the on-time KPI tile decision used by
// <SupplierScorecardModal>. The backend deliberately reports on_time_count
// and unscheduled_count so the UI can disambiguate a genuine 0% on-time
// record from "nothing was schedulable"; this locks that behaviour in.

import { describe, it, expect } from 'vitest';

import { onTimeTileModel } from './SupplierScorecardModal';

describe('onTimeTileModel', () => {
  it('reports a measured tile when there is a schedulable denominator', () => {
    const model = onTimeTileModel({
      total_gr_count: 4,
      unscheduled_count: 1,
      on_time_count: 3,
      on_time_delivery_pct: 1.0,
    });
    expect(model.kind).toBe('measured');
    // 3/3 scheduled on time -> success tone (>= 0.9).
    expect(model.tone).toBe('success');
    // Denominator excludes the one unscheduled GR.
    expect(model.scheduled).toBe(3);
  });

  it('flags a poor measured on-time record as a risk', () => {
    const model = onTimeTileModel({
      total_gr_count: 2,
      unscheduled_count: 0,
      on_time_count: 0,
      on_time_delivery_pct: 0.0,
    });
    expect(model.kind).toBe('measured');
    expect(model.tone).toBe('error');
    expect(model.scheduled).toBe(2);
  });

  it('does NOT show 0% as risk when every delivery was unscheduled', () => {
    // Regression: the backend returns on_time_delivery_pct == 0.0 for a
    // supplier whose deliveries all lack a scheduled date. Rendering that as
    // a red 0% tile slanders a supplier that simply had nothing to measure.
    const model = onTimeTileModel({
      total_gr_count: 3,
      unscheduled_count: 3,
      on_time_count: 0,
      on_time_delivery_pct: 0.0,
    });
    expect(model.kind).toBe('unscheduled_only');
    expect(model.tone).toBe('neutral');
    expect(model.scheduled).toBe(0);
  });

  it('reports no_deliveries when there are no goods receipts at all', () => {
    const model = onTimeTileModel({
      total_gr_count: 0,
      unscheduled_count: 0,
      on_time_count: 0,
      on_time_delivery_pct: 0.0,
    });
    expect(model.kind).toBe('no_deliveries');
    expect(model.tone).toBe('neutral');
    expect(model.scheduled).toBe(0);
  });
});
