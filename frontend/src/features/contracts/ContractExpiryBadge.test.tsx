// DDC-CWICR-OE: DataDrivenConstruction / OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for <ContractExpiryBadge>.
//
// Mirrors the DeliveryCountdownBadge test pattern: pin UTC midnight on
// the test clock, then assert each branch (expired / soon / hidden /
// terminal status / null date / malformed date).

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render } from '@testing-library/react';

import { ContractExpiryBadge } from './ContractExpiryBadge';

const FIXED_NOW = new Date('2026-05-25T00:00:00Z');

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(FIXED_NOW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe('<ContractExpiryBadge>', () => {
  it('renders nothing when end_date is null', () => {
    const { container } = render(
      <ContractExpiryBadge endDate={null} status="active" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a completed contract even if expired', () => {
    const { container } = render(
      <ContractExpiryBadge endDate="2026-04-01" status="completed" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a terminated contract even if expired', () => {
    const { container } = render(
      <ContractExpiryBadge endDate="2026-04-01" status="terminated" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for a draft contract - not live yet', () => {
    const { container } = render(
      <ContractExpiryBadge endDate="2026-04-01" status="draft" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('flags expired contracts with a red badge', () => {
    const { container } = render(
      <ContractExpiryBadge endDate="2026-04-01" status="active" />,
    );
    expect(container.textContent).toMatch(/Expired/i);
  });

  it('flags contracts expiring inside the 30-day amber window', () => {
    const { container } = render(
      <ContractExpiryBadge endDate="2026-06-10" status="active" />,
    );
    expect(container.textContent).toMatch(/Expires/i);
  });

  it('renders nothing when end_date is comfortably far away', () => {
    const { container } = render(
      <ContractExpiryBadge endDate="2027-01-01" status="active" />,
    );
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing for malformed dates', () => {
    const { container } = render(
      <ContractExpiryBadge endDate="not-a-date" status="active" />,
    );
    expect(container.firstChild).toBeNull();
  });
});
