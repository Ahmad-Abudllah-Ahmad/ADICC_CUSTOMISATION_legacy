// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Tests for TabBar — the shared accessible tab strip used by module
// pages to satisfy WCAG 2.1.1 (keyboard) and the WAI-ARIA "tabs" pattern.

import { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { TabBar, tabIds } from './TabBar';

type TabId = 'overview' | 'details' | 'history';

function harness(initial: TabId = 'overview') {
  const onChange = vi.fn();
  function Harness() {
    const [active, setActive] = useState<TabId>(initial);
    return (
      <>
        <TabBar<TabId>
          ariaLabel="Module sections"
          idPrefix="hx"
          tabs={[
            { id: 'overview', label: 'Overview' },
            { id: 'details', label: 'Details' },
            { id: 'history', label: 'History', disabled: true },
          ]}
          activeId={active}
          onChange={(next) => {
            onChange(next);
            setActive(next);
          }}
        />
        <div
          role="tabpanel"
          id={tabIds('hx').panelId(active)}
          aria-labelledby={tabIds('hx').tabId(active)}
        >
          Active panel: {active}
        </div>
      </>
    );
  }
  return { onChange, ...render(<Harness />) };
}

describe('TabBar', () => {
  it('renders a tablist with all tabs and the right ARIA wiring', () => {
    harness();
    const tablist = screen.getByRole('tablist', { name: 'Module sections' });
    expect(tablist).toBeInTheDocument();

    const overview = screen.getByRole('tab', { name: 'Overview' });
    const details = screen.getByRole('tab', { name: 'Details' });
    const history = screen.getByRole('tab', { name: 'History' });

    expect(overview).toHaveAttribute('aria-selected', 'true');
    expect(details).toHaveAttribute('aria-selected', 'false');
    expect(history).toHaveAttribute('aria-disabled', 'true');

    // Only the active tab is in the page tab stop (roving tabindex)
    expect(overview).toHaveAttribute('tabindex', '0');
    expect(details).toHaveAttribute('tabindex', '-1');
    expect(history).toHaveAttribute('tabindex', '-1');

    // Panel is wired to the active tab id
    const panel = screen.getByRole('tabpanel');
    expect(panel).toHaveAttribute('aria-labelledby', 'hx-tab-overview');
    expect(overview).toHaveAttribute('aria-controls', 'hx-panel-overview');
  });

  it('clicking a tab activates it', () => {
    const { onChange } = harness();
    fireEvent.click(screen.getByRole('tab', { name: 'Details' }));
    expect(onChange).toHaveBeenCalledWith('details');
    expect(screen.getByRole('tab', { name: 'Details' })).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  it('ArrowRight moves to the next enabled tab and skips disabled ones', () => {
    const { onChange } = harness('overview');
    const tablist = screen.getByRole('tablist');
    fireEvent.keyDown(tablist, { key: 'ArrowRight' });
    // overview -> details (history is disabled)
    expect(onChange).toHaveBeenLastCalledWith('details');
  });

  it('ArrowLeft wraps to the last enabled tab from the first', () => {
    const { onChange } = harness('overview');
    const tablist = screen.getByRole('tablist');
    fireEvent.keyDown(tablist, { key: 'ArrowLeft' });
    // overview is index 0 of the enabled list (overview, details);
    // ArrowLeft wraps to the last enabled which is "details".
    expect(onChange).toHaveBeenLastCalledWith('details');
  });

  it('Home jumps to the first enabled tab; End jumps to the last enabled tab', () => {
    const { onChange } = harness('details');
    const tablist = screen.getByRole('tablist');
    fireEvent.keyDown(tablist, { key: 'Home' });
    expect(onChange).toHaveBeenLastCalledWith('overview');
    fireEvent.keyDown(tablist, { key: 'End' });
    expect(onChange).toHaveBeenLastCalledWith('details');
  });

  it('clicking a disabled tab does not change selection', () => {
    const { onChange } = harness('overview');
    fireEvent.click(screen.getByRole('tab', { name: 'History' }));
    expect(onChange).not.toHaveBeenCalled();
  });
});
