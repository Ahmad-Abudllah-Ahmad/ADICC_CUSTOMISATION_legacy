/**
 * Tests for the shared DismissibleInfo help card.
 *
 * Behaviour under test (the 2026-06-06 contract):
 *   - clicking the card collapses it - NOTHING is left in the page; the card
 *     registers itself in useModuleInfoStore so the TOP APP BAR can show the
 *     re-opener icon (project pill > module name > info icon)
 *   - the X ALSO just collapses (it never hides the card forever)
 *   - the store's expand entry re-expands the card and unregisters it
 *   - a legacy localStorage value of "2" (old "dismissed") maps to collapsed
 *   - a stored "1" maps to collapsed
 *   - clicking an inner link pill runs its handler WITHOUT toggling the card
 *   - unmount (navigation) unregisters from the store
 *
 * ``react-i18next`` and ``window.localStorage`` are mocked globally in
 * ``src/test/setup.ts`` (t returns ``defaultValue``; localStorage is an
 * in-memory store with a working ``clear()``).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

import { DismissibleInfo } from './DismissibleInfo';
import { useModuleInfoStore } from '@/stores/useModuleInfoStore';

const KEY = 'demo-card';
const LS_KEY = `oce.intro.${KEY}`;

function renderCard(props?: { links?: { label: string; onClick: () => void }[] }) {
  return render(
    <DismissibleInfo storageKey={KEY} title="Demo title" links={props?.links}>
      <span>Body copy explaining the page.</span>
    </DismissibleInfo>,
  );
}

/** The store registry of collapsed cards (what the Header icon reads). */
function storeEntries() {
  return useModuleInfoStore.getState().entries;
}

/** The clickable surface for "whole-card click" in the expanded state. */
function cardClickSurface(): HTMLElement {
  const wrapper = document.querySelector('div.border-l-oe-blue\\/70') as HTMLElement | null;
  if (!wrapper) throw new Error('no expanded card wrapper rendered');
  // First element child is the flex row that carries the collapse click handler.
  return wrapper.firstElementChild as HTMLElement;
}

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
  useModuleInfoStore.setState({ entries: [] });
});

describe('DismissibleInfo', () => {
  it('renders expanded by default with title, body and an expanded toggle', () => {
    renderCard();
    expect(screen.getByText('Demo title')).toBeInTheDocument();
    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
    // A toggle marked aria-expanded carries the collapse semantics for AT.
    expect(document.querySelector('[aria-expanded="true"]')).toBeInTheDocument();
    // Nothing registered while expanded - the top bar shows no icon.
    expect(storeEntries()).toHaveLength(0);
  });

  it('clicking anywhere on the card collapses it to NOTHING and persists "1"', () => {
    const { container } = renderCard();
    // Click the whole-card surface (not just the title) to prove the entire
    // card is the toggle.
    fireEvent.click(cardClickSurface());

    // The card leaves the page entirely - no leftover line (founder decision
    // 2026-06-06: the re-opener lives in the top app bar instead).
    expect(screen.queryByText('Body copy explaining the page.')).not.toBeInTheDocument();
    expect(screen.queryByText('Demo title')).not.toBeInTheDocument();
    expect(screen.queryByText('Module information')).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
    // Collapsed state persisted under "1".
    expect(window.localStorage.getItem(LS_KEY)).toBe('1');
    // Registered for the top-bar icon.
    expect(storeEntries()).toHaveLength(1);
    expect(storeEntries()[0]!.key).toBe(LS_KEY);
  });

  it('the store expand entry (top-bar icon) re-expands and persists "0"', () => {
    renderCard();
    fireEvent.click(cardClickSurface());
    expect(storeEntries()).toHaveLength(1);

    // The Header icon calls expandAll(), which fires the registered expand.
    act(() => useModuleInfoStore.getState().expandAll());

    expect(screen.getByText('Demo title')).toBeInTheDocument();
    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBe('0');
    // Expanded card unregisters - the top-bar icon disappears.
    expect(storeEntries()).toHaveLength(0);
  });

  it('the X collapses the card (it never hides it forever) and persists "1"', () => {
    const { unmount } = renderCard();
    const collapseBtn = screen.getByRole('button', { name: /collapse/i });
    fireEvent.click(collapseBtn);

    // Gone from the page, registered for the top bar.
    expect(screen.queryByText('Body copy explaining the page.')).not.toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBe('1');
    expect(storeEntries()).toHaveLength(1);

    // Remount with the SAME storageKey -> still collapsed, still registered.
    unmount();
    expect(storeEntries()).toHaveLength(0); // unmount unregistered
    renderCard();
    expect(screen.queryByText('Demo title')).not.toBeInTheDocument();
    expect(storeEntries()).toHaveLength(1);
  });

  it('legacy stored "1" maps to collapsed (nothing in page, registered)', () => {
    window.localStorage.setItem(LS_KEY, '1');
    const { container } = renderCard();

    expect(container.firstChild).toBeNull();
    expect(storeEntries()).toHaveLength(1);
  });

  it('legacy stored "2" (old "dismissed") maps to collapsed and stays reachable', () => {
    window.localStorage.setItem(LS_KEY, '2');
    const { container } = renderCard();

    // No longer hidden forever: registered, so the top-bar icon re-opens it.
    expect(container.firstChild).toBeNull();
    expect(storeEntries()).toHaveLength(1);
    act(() => useModuleInfoStore.getState().expandAll());
    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
  });

  it('unmount while collapsed unregisters from the store (navigation)', () => {
    window.localStorage.setItem(LS_KEY, '1');
    const { unmount } = renderCard();
    expect(storeEntries()).toHaveLength(1);
    unmount();
    expect(storeEntries()).toHaveLength(0);
  });

  it('clicking an inner link pill runs its handler WITHOUT toggling the card', () => {
    const onClick = vi.fn();
    renderCard({ links: [{ label: 'Open BOQ', onClick }] });

    const pill = screen.getByRole('button', { name: 'Open BOQ' });
    fireEvent.click(pill);

    // Handler fired, but the card stayed expanded (body still visible) and
    // nothing was persisted (still no toggle write).
    expect(onClick).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Body copy explaining the page.')).toBeInTheDocument();
    expect(window.localStorage.getItem(LS_KEY)).toBeNull();
    expect(storeEntries()).toHaveLength(0);
  });

  it('two cards with different keys keep independent state and registrations', () => {
    render(
      <>
        <DismissibleInfo storageKey="a" title="Card A" />
        <DismissibleInfo storageKey="b" title="Card B" />
      </>,
    );
    // Collapse only card A via its X (collapse) button.
    const collapseButtons = screen.getAllByRole('button', { name: /collapse/i });
    expect(collapseButtons).toHaveLength(2);
    fireEvent.click(collapseButtons[0]!);

    // Card A gone from the page and registered; Card B still expanded.
    expect(screen.queryByText('Card A')).not.toBeInTheDocument();
    expect(screen.getByText('Card B')).toBeInTheDocument();
    expect(window.localStorage.getItem('oce.intro.a')).toBe('1');
    expect(window.localStorage.getItem('oce.intro.b')).toBeNull();
    expect(storeEntries()).toHaveLength(1);
    expect(storeEntries()[0]!.key).toBe('oce.intro.a');
  });
});
