// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import type { ControlsKPI } from '../api';
import { ControlsTile } from '../ControlsTile';

function makeKpi(overrides: Partial<ControlsKPI> = {}): ControlsKPI {
  return {
    code: 'cpi',
    label: 'Cost Performance Index',
    value: '0.97',
    unit: 'ratio',
    status: 'amber',
    source_record_count: 12,
    breakdown: {},
    drill_url: '/api/v1/project-controls/drill/cpi',
    ...overrides,
  };
}

describe('ControlsTile', () => {
  it('renders the label, formatted value and record count', () => {
    render(<ControlsTile kpi={makeKpi()} onDrill={vi.fn()} />);
    expect(screen.getByText('Cost Performance Index')).toBeInTheDocument();
    expect(screen.getByText('0.97')).toBeInTheDocument();
    expect(screen.getByText('12 records')).toBeInTheDocument();
  });

  it('fires onDrill when clicked', () => {
    const onDrill = vi.fn();
    const kpi = makeKpi();
    render(<ControlsTile kpi={kpi} onDrill={onDrill} />);
    fireEvent.click(screen.getByRole('button'));
    expect(onDrill).toHaveBeenCalledWith(kpi);
  });

  it('shows a dash and "no data" when there are no source records', () => {
    render(
      <ControlsTile kpi={makeKpi({ source_record_count: 0 })} onDrill={vi.fn()} />,
    );
    expect(screen.getByText('—')).toBeInTheDocument();
    expect(screen.getByText('no data')).toBeInTheDocument();
  });

  it('formats currency with its ISO code from the breakdown', () => {
    const kpi = makeKpi({
      code: 'risk_open_exposure',
      unit: 'currency',
      value: '15000',
      breakdown: { currency: 'EUR' },
    });
    render(<ControlsTile kpi={kpi} onDrill={vi.fn()} />);
    expect(screen.getByText('EUR 15.0k')).toBeInTheDocument();
  });

  it('renders the multi-currency split for portfolio money KPIs', () => {
    const kpi = makeKpi({
      code: 'pending_variation_value',
      unit: 'currency',
      value: '2000',
      breakdown: {
        currency: 'USD',
        multi_currency: true,
        by_currency: { EUR: '1000', USD: '2000' },
      },
    });
    render(<ControlsTile kpi={kpi} onDrill={vi.fn()} />);
    expect(screen.getByText('multi-currency')).toBeInTheDocument();
    expect(screen.getByText('EUR')).toBeInTheDocument();
    expect(screen.getByText('USD')).toBeInTheDocument();
  });
});
