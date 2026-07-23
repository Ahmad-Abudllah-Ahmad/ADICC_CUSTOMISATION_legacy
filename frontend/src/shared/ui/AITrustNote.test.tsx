// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Pins the user-visible contract of the shared AI trust + feedback strip:
// it always shows the "data stays in your project" reassurance, shows a
// confidence badge only when a real score is given, and posts a correct /
// incorrect verdict (with surface + ref + project) to the generic feedback
// sink.

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// Stub the api + toast modules BEFORE importing the component so its imports
// bind to the spies.
vi.mock('@/shared/lib/api', () => ({
  apiPost: vi.fn().mockResolvedValue({ id: 'fb-1', surface: 'ai_estimator', correct: true }),
}));

const addToast = vi.fn();
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: (selector: (s: { addToast: typeof addToast }) => unknown) =>
    selector({ addToast }),
}));

import { apiPost } from '@/shared/lib/api';
import { AITrustNote } from './AITrustNote';

const apiPostSpy = apiPost as ReturnType<typeof vi.fn>;

function renderNote(props: Partial<React.ComponentProps<typeof AITrustNote>> = {}) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AITrustNote surface="ai_estimator" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  cleanup();
});

describe('AITrustNote', () => {
  it('always shows the data-residency reassurance', () => {
    renderNote();
    expect(screen.getByText('Your data stays in your project.')).toBeInTheDocument();
  });

  it('renders a custom produced-by line when given', () => {
    renderNote({ producedBy: 'Grounded in your cost database.' });
    expect(screen.getByText('Grounded in your cost database.')).toBeInTheDocument();
  });

  it('shows a confidence badge only when a real score is provided', () => {
    const { rerender } = renderNote({ confidence: 0.91 });
    expect(screen.getByText('High confidence')).toBeInTheDocument();

    const qc = new QueryClient();
    rerender(
      <QueryClientProvider client={qc}>
        <AITrustNote surface="ai_estimator" />
      </QueryClientProvider>,
    );
    expect(screen.queryByText('High confidence')).toBeNull();
  });

  it('posts a correct verdict with surface, ref, project and note', async () => {
    renderNote({ refId: 'run-7', projectId: 'proj-3' });

    fireEvent.change(screen.getByLabelText('Optional feedback note'), {
      target: { value: 'Rates matched the tender.' },
    });
    fireEvent.click(screen.getByText('Helpful'));

    await waitFor(() => expect(apiPostSpy).toHaveBeenCalledTimes(1));
    expect(apiPostSpy).toHaveBeenCalledWith('/v1/ai-agents/feedback', {
      surface: 'ai_estimator',
      correct: true,
      ref: 'run-7',
      project_id: 'proj-3',
      note: 'Rates matched the tender.',
    });
    // Collapses to the recorded confirmation afterwards.
    await screen.findByText('You marked this helpful');
  });

  it('can be rendered without the feedback verdict', () => {
    renderNote({ showFeedback: false });
    expect(screen.queryByText('Was this helpful?')).toBeNull();
    expect(screen.getByText('Your data stays in your project.')).toBeInTheDocument();
  });
});
