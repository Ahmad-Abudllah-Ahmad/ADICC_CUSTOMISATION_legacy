// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <DeliveryCountdownBadge>.
//
// Pins the system clock so the date arithmetic is deterministic. The
// badge does its math in UTC (Date.UTC + getUTCFullYear, ...), so
// freezing UTC midnight is enough - no need to spoof timezones.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';

import { DeliveryCountdownBadge } from './DeliveryCountdownBadge';

const FIXED_NOW = new Date('2026-05-25T00:00:00Z');

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(FIXED_NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('<DeliveryCountdownBadge>', () => {
  it('renders nothing when delivery_date is null', () => {
    const { container } = render(
      <DeliveryCountdownBadge deliveryDate={null} status="issued" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a completed PO even if overdue', () => {
    const { container } = render(
      <DeliveryCountdownBadge deliveryDate="2026-05-20" status="completed" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a cancelled PO', () => {
    const { container } = render(
      <DeliveryCountdownBadge deliveryDate="2026-05-20" status="cancelled" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when delivery is more than a week out', () => {
    const { container } = render(
      <DeliveryCountdownBadge deliveryDate="2026-07-01" status="issued" />,
    );
    expect(container.firstChild).toBeNull();
  });

  // The shared vitest setup mocks react-i18next with a `t` that returns
  // the `defaultValue` template verbatim (no interpolation). We assert
  // the badge picks the right branch by matching the template string;
  // production runtime substitutes {{days}} via i18next.
  it('flags overdue with day count', () => {
    const { container } = render(
      <DeliveryCountdownBadge deliveryDate="2026-05-20" status="issued" />,
    );
    expect(container.textContent).toMatch(/Overdue/i);
  });

  it('flags due-today', () => {
    const { container } = render(
      <DeliveryCountdownBadge deliveryDate="2026-05-25" status="issued" />,
    );
    expect(container.textContent).toMatch(/Due today/i);
  });

  it('flags due-in-N-days when within a week', () => {
    const { container } = render(
      <DeliveryCountdownBadge deliveryDate="2026-05-28" status="issued" />,
    );
    expect(container.textContent).toMatch(/^In\s*/i);
  });

  it('renders nothing for malformed dates', () => {
    const { container } = render(
      <DeliveryCountdownBadge deliveryDate="not-a-date" status="issued" />,
    );
    expect(container.firstChild).toBeNull();
  });
});
