// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../api', () => ({
  getTimeFactors: vi.fn(),
  putTimeFactors: vi.fn(),
}));

vi.mock('@/shared/lib/api', () => ({
  apiGet: vi.fn(),
  apiPut: vi.fn(),
  getErrorMessage: (e: unknown) => String(e),
}));

const addToast = vi.fn();
vi.mock('@/stores/useToastStore', () => ({
  useToastStore: (sel: (s: { addToast: typeof addToast }) => unknown) => sel({ addToast }),
}));

import { getTimeFactors, putTimeFactors } from '../api';
import { TimeFactorsEditor } from '../TimeFactorsEditor';

function renderEditor() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TimeFactorsEditor open onClose={() => {}} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getTimeFactors).mockResolvedValue({
    factors: [
      { module: 'rfi', action: 'rfi_answered', minutes: '25', default_minutes: '25', is_override: false },
      {
        module: 'takeoff',
        action: 'takeoff_parsed',
        minutes: '50',
        default_minutes: '35',
        is_override: true,
      },
    ],
  });
  vi.mocked(putTimeFactors).mockResolvedValue({
    factors: [
      { module: 'rfi', action: 'rfi_answered', minutes: '40', default_minutes: '25', is_override: true },
      {
        module: 'takeoff',
        action: 'takeoff_parsed',
        minutes: '50',
        default_minutes: '35',
        is_override: true,
      },
    ],
  });
});

describe('TimeFactorsEditor', () => {
  it('lists factors with the tuned badge and the default hint', async () => {
    renderEditor();
    await waitFor(() => {
      expect(screen.getByText('RFI answered')).toBeInTheDocument();
    });
    expect(screen.getByText('Takeoff parsed')).toBeInTheDocument();
    // The overridden row carries a Tuned badge; the default-valued row does not.
    expect(screen.getByText('Tuned')).toBeInTheDocument();
  });

  it('sends only the changed factor on save', async () => {
    renderEditor();
    const input = (await screen.findByLabelText(/Minutes for RFI answered/i)) as HTMLInputElement;
    fireEvent.change(input, { target: { value: '40' } });

    fireEvent.click(screen.getByRole('button', { name: /Save factors/i }));

    await waitFor(() => {
      expect(putTimeFactors).toHaveBeenCalledTimes(1);
    });
    // Only the edited pair is sent (the unchanged takeoff row is not). react-query
    // passes a context object as the second mutate arg, so assert the first arg.
    expect(vi.mocked(putTimeFactors).mock.calls[0]![0]).toEqual([
      { module: 'rfi', action: 'rfi_answered', minutes: '40' },
    ]);
  });

  it('disables save when there are no changes', async () => {
    renderEditor();
    await screen.findByText('RFI answered');
    expect(screen.getByRole('button', { name: /Save factors/i })).toBeDisabled();
  });
});
