// @ts-nocheck
// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests the project-settings active-methodology switcher: it lists the
// methodologies visible to the project, shows the currently-active slug, and
// PUTs the new slug when changed and saved.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../api', () => ({
  toNum: (v: unknown) => (typeof v === 'number' ? v : Number(v) || 0),
  methodologyApi: {
    list: vi.fn(),
    getActive: vi.fn(),
    setActive: vi.fn(),
  },
}));

import { methodologyApi } from '../api';
import { MethodologyActiveCard } from '../MethodologyActiveCard';

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MethodologyActiveCard projectId="proj-1" />
    </QueryClientProvider>,
  );
}

describe('MethodologyActiveCard', () => {
  beforeEach(() => {
    (methodologyApi.list as ReturnType<typeof vi.fn>).mockReset();
    (methodologyApi.getActive as ReturnType<typeof vi.fn>).mockReset();
    (methodologyApi.setActive as ReturnType<typeof vi.fn>).mockReset();

    (methodologyApi.list as ReturnType<typeof vi.fn>).mockResolvedValue([
      {
        id: 'meth-1',
        slug: 'germany-proj1',
        scope: 'project',
        project_id: 'proj-1',
        country_code: 'DE',
        industry: null,
        name: 'Our Germany method',
        currency: 'EUR',
        is_builtin: false,
        is_editable: true,
      },
    ]);
    (methodologyApi.getActive as ReturnType<typeof vi.fn>).mockResolvedValue({
      project_id: 'proj-1',
      methodology_slug: 'international',
    });
  });

  it('shows the current active slug', async () => {
    renderCard();
    // The current-active badge renders the active slug.
    expect(await screen.findByText('international')).toBeInTheDocument();
  });

  it('disables Save until the selection changes, then PUTs the new slug', async () => {
    (methodologyApi.setActive as ReturnType<typeof vi.fn>).mockResolvedValue({
      project_id: 'proj-1',
      methodology_slug: 'germany-proj1',
    });

    renderCard();
    // Wait for the select to render (it only appears once both the list and
    // active queries resolve - the badge alone renders before that).
    const select = await screen.findByRole('combobox');

    const save = screen.getByRole('button', { name: /Save/ });
    expect(save).toBeDisabled();

    fireEvent.change(select, { target: { value: 'germany-proj1' } });

    expect(save).not.toBeDisabled();
    fireEvent.click(save);

    await waitFor(() => {
      expect(methodologyApi.setActive).toHaveBeenCalledWith('proj-1', 'germany-proj1');
    });
  });
});
