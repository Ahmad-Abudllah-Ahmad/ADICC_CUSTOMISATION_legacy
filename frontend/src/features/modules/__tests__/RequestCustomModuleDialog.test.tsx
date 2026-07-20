// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for RequestCustomModuleDialog — the full-screen "Request a
// custom module" modal launched from the sidebar CTA.
//
// Behaviour covered:
//   1. Renders nothing when open=false (no DOM impact).
//   2. Renders the hero, both option cards and the dev-guide footer
//      when open=true.
//   3. Each option card is an anchor pointing at the corresponding
//      hosted contact form on adicc-uae.com (the canonical
//      product marketing site), with target=_blank and rel=noopener
//      (security baseline).
//   4. Clicking an option card invokes onClose so the modal dismisses
//      while the new tab opens.
//   5. Escape closes the modal.
//   6. Background scroll is locked while the modal is open and
//      restored when it closes / unmounts.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

import { RequestCustomModuleDialog } from '../RequestCustomModuleDialog';

// ── Helpers ─────────────────────────────────────────────────────────

function renderDialog(open = true) {
  const onClose = vi.fn();
  const utils = render(
    <MemoryRouter>
      <RequestCustomModuleDialog open={open} onClose={onClose} />
    </MemoryRouter>,
  );
  return { onClose, ...utils };
}

// ── Tests ───────────────────────────────────────────────────────────

describe('RequestCustomModuleDialog', () => {
  beforeEach(() => {
    // Reset body overflow between tests — the modal locks it on open.
    document.body.style.overflow = '';
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.style.overflow = '';
  });

  it('renders nothing when open=false', () => {
    renderDialog(false);
    expect(
      screen.queryByRole('dialog', { name: /Tell us what your team needs/i }),
    ).toBeNull();
  });

  it('renders the hero, both option cards and the dev-guide footer', () => {
    renderDialog(true);
    expect(
      screen.getByRole('dialog', { name: /Tell us what your team needs/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /Could help other teams too/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: /Built just for our company/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /Open developer guide/i }),
    ).toBeInTheDocument();
  });

  it('community option points at the public contact form with utm tags', () => {
    renderDialog(true);
    const link = screen.getByRole('link', {
      name: /Propose on our roadmap/i,
    });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'));
    // Pinned at adicc-uae.com — the canonical product
    // marketing site. The pin catches accidental regressions back to
    // the placeholder adicc-uae.com / openestimate.io properties
    // (parked / 405 as of 2026-05-13).
    expect(link.getAttribute('href')).toMatch(
      /openconstructionerp\.com\/contact\?topic=module_proposal_public/,
    );
    expect(link.getAttribute('href')).toMatch(/utm_source=oe_app/);
  });

  it('private option points at the bespoke contact form with the right topic', () => {
    renderDialog(true);
    const link = screen.getByRole('link', {
      name: /Request a scope & quote/i,
    });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('href')).toMatch(
      /topic=module_proposal_private/,
    );
  });

  it('clicking an option card invokes onClose', async () => {
    const user = userEvent.setup();
    const { onClose } = renderDialog(true);
    const link = screen.getByRole('link', {
      name: /Propose on our roadmap/i,
    });
    // Prevent the test runner from following the external href.
    link.addEventListener('click', (e) => e.preventDefault());
    await user.click(link);
    expect(onClose).toHaveBeenCalled();
  });

  it('Escape closes the dialog', () => {
    const { onClose } = renderDialog(true);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('locks body scroll while open and restores it on unmount', () => {
    document.body.style.overflow = '';
    const { unmount } = render(
      <MemoryRouter>
        <RequestCustomModuleDialog open={true} onClose={() => undefined} />
      </MemoryRouter>,
    );
    expect(document.body.style.overflow).toBe('hidden');
    unmount();
    // The cleanup effect restores the previous overflow value (was '').
    expect(document.body.style.overflow).toBe('');
  });

  it('clicking the backdrop closes the dialog but clicking the inner panel does not', async () => {
    const user = userEvent.setup();
    const { onClose } = renderDialog(true);
    // The inner panel is the role="dialog" element's first child. Click on
    // the dialog root (which is the backdrop) closes; click on inner does not.
    const dialog = screen.getByRole('dialog', {
      name: /Tell us what your team needs/i,
    });
    // Inner panel — find by querying a child heading and walking up.
    const heroHeading = screen.getByRole('heading', {
      name: /Tell us what your team needs/i,
    });
    await user.click(heroHeading); // inner panel → should NOT close
    expect(onClose).not.toHaveBeenCalled();
    // Click directly on the backdrop (the dialog root itself).
    fireEvent.click(dialog);
    expect(onClose).toHaveBeenCalled();
  });
});
