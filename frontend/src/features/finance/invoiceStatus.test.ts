// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect } from 'vitest';
import {
  invoiceStatusOptions,
  INVOICE_SELF_SERVICE_TRANSITIONS,
  INVOICE_STATUS_ORDER,
} from './FinancePage';

/**
 * #284: a freshly created invoice lands in 'draft' and previously had no
 * control to advance its status (the row Approve / Mark Paid buttons only show
 * from 'pending' / 'approved'). The edit-modal status dropdown fills that gap,
 * but it must NEVER offer the privileged 'approved' / 'paid' transitions -
 * those go through the manager-gated /approve and /pay endpoints (and /pay
 * writes a binding ledger entry). These tests lock that invariant in.
 */
describe('invoice status dropdown options', () => {
  it('offers draft -> pending so a new invoice can move forward', () => {
    const opts = invoiceStatusOptions('draft');
    expect(opts).toContain('draft'); // current is always present
    expect(opts).toContain('pending');
    expect(opts).toContain('cancelled');
  });

  it('lets a pending invoice go back to draft or be cancelled', () => {
    const opts = invoiceStatusOptions('pending');
    expect(opts).toEqual(expect.arrayContaining(['pending', 'draft', 'cancelled']));
  });

  it('lets a cancelled invoice be re-opened to draft', () => {
    expect(invoiceStatusOptions('cancelled')).toEqual(
      expect.arrayContaining(['cancelled', 'draft']),
    );
  });

  it('NEVER offers approve or pay from the dropdown (manager-gated only)', () => {
    for (const status of INVOICE_STATUS_ORDER) {
      const opts = invoiceStatusOptions(status);
      const reachable = opts.filter((o) => o !== status);
      expect(reachable).not.toContain('approved');
      expect(reachable).not.toContain('paid');
    }
  });

  it('returns only the current status when there is no editor-safe next step', () => {
    // approved / paid are terminal from the dropdown's perspective: the only
    // option is the current status, which the UI renders read-only.
    expect(invoiceStatusOptions('approved')).toEqual(['approved']);
    expect(invoiceStatusOptions('paid')).toEqual(['paid']);
  });

  it('keeps the self-service map a strict subset of the lifecycle vocabulary', () => {
    for (const [from, tos] of Object.entries(INVOICE_SELF_SERVICE_TRANSITIONS)) {
      expect(INVOICE_STATUS_ORDER).toContain(from);
      for (const to of tos) {
        expect(INVOICE_STATUS_ORDER).toContain(to);
      }
    }
  });

  it('preserves the canonical display order in the option list', () => {
    // draft has options draft, pending, cancelled - they must come back in
    // INVOICE_STATUS_ORDER order, not transition-map order.
    expect(invoiceStatusOptions('draft')).toEqual(['draft', 'pending', 'cancelled']);
  });
});
