// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';

// Resolve a project id from the context store without a real store.
vi.mock('@/stores/useProjectContextStore', () => ({
  useProjectContextStore: (sel: (s: { activeProjectId: string }) => unknown) => sel({ activeProjectId: 'p-1' }),
}));

vi.mock('../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api')>();
  return {
    ...actual,
    searchRecords: vi.fn(),
  };
});

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

import { searchRecords } from '../api';
import { RetrievalPage } from '../RetrievalPage';

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/find']}>
        <RetrievalPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  // Search history is localStorage-backed; clear it so saved/recent state from
  // one test never leaks into the next.
  localStorage.clear();
  vi.mocked(searchRecords).mockResolvedValue({
    count: 1,
    results: [
      {
        record_type: 'change_order',
        record_id: 'co-7',
        title: 'Additional rebar to core wall',
        snippet: 'Add rebar to the core wall.',
        source_module: 'changeorders',
        party: 'contractor-a',
        occurred_at: '2026-06-20T00:00:00Z',
        entity_refs: ['CO-7'],
        score: 0.83,
        matched_facets: ['text'],
        provenance: { module: 'changeorders', record_id: 'co-7' },
      },
    ],
  });
});

describe('RetrievalPage', () => {
  it('renders the search box and a starter empty state before any search', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: /Find Records/i })).toBeInTheDocument();
    expect(screen.getByPlaceholderText(/Search the project record/i)).toBeInTheDocument();
    // No search has been committed yet, so the starter prompt shows.
    expect(screen.getByText(/Enter a term or open Filters/i)).toBeInTheDocument();
    expect(searchRecords).not.toHaveBeenCalled();
  });

  it('runs a search and renders ranked results with provenance facets', async () => {
    renderPage();
    fireEvent.change(screen.getByPlaceholderText(/Search the project record/i), {
      target: { value: 'rebar' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Search$/i }));

    // The title is a deep-link to the owning module, and the query term is
    // highlighted inside it (so the text is split by a <mark>); assert on the
    // link's accessible name, which concatenates the whole title.
    const titleLink = await screen.findByRole('link', {
      name: 'Additional rebar to core wall',
    });
    expect(titleLink).toHaveAttribute('href', '/changeorders');
    expect(searchRecords).toHaveBeenCalledWith('p-1', expect.objectContaining({ text: 'rebar' }));
    // The snippet is likewise split by the highlight mark, so match on the
    // paragraph's full text content.
    expect(
      screen.getByText(
        (_content, el) =>
          el?.tagName === 'P' && el?.textContent === 'Add rebar to the core wall.',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('CO-7')).toBeInTheDocument();
    expect(screen.getByText(/1 results/i)).toBeInTheDocument();
  });
});
