// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
/**
 * YamlEditor unit tests.
 *
 * Covers the small surface area of the textarea-based editor:
 *  - content renders into the textarea
 *  - Tab inserts two spaces (and prevents the default focus-shift)
 *  - the side gutter renders 1-indexed line numbers per row
 *  - the inline error banner shows the supplied error
 *  - readonly mode disables editing
 *  - the "parsed" badge renders when parsed=true and no error
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import { YamlEditor } from '../YamlEditor';

beforeEach(() => {
  cleanup();
});

describe('YamlEditor', () => {
  it('renders the provided content in the textarea', () => {
    render(<YamlEditor value="hello: world" />);
    const ta = screen.getByTestId('yaml-editor-textarea') as HTMLTextAreaElement;
    expect(ta.value).toBe('hello: world');
  });

  it('inserts two spaces when Tab is pressed', () => {
    const onChange = vi.fn();
    render(<YamlEditor value="abc" onChange={onChange} />);
    const ta = screen.getByTestId('yaml-editor-textarea') as HTMLTextAreaElement;
    ta.focus();
    // Caret at the very start.
    ta.setSelectionRange(0, 0);
    fireEvent.keyDown(ta, { key: 'Tab' });
    expect(onChange).toHaveBeenCalledTimes(1);
    expect(onChange).toHaveBeenCalledWith('  abc');
  });

  it('renders one gutter line per row', () => {
    render(<YamlEditor value={'a\nb\nc'} />);
    const gutter = screen.getByTestId('yaml-editor-gutter');
    // Three rows → three line-number divs.
    expect(gutter.querySelectorAll('div').length).toBe(3);
    expect(screen.getByTestId('yaml-editor-line-1')).toBeTruthy();
    expect(screen.getByTestId('yaml-editor-line-3')).toBeTruthy();
  });

  it('shows the inline error banner when error is set', () => {
    render(<YamlEditor value="bad: : :" error="parse failed" />);
    const banner = screen.getByTestId('yaml-editor-error');
    expect(banner.textContent).toContain('parse failed');
  });

  it('disables editing in readonly mode', () => {
    const onChange = vi.fn();
    render(<YamlEditor value="x" readonly onChange={onChange} />);
    const ta = screen.getByTestId('yaml-editor-textarea') as HTMLTextAreaElement;
    expect(ta.readOnly).toBe(true);
    // Tab handler short-circuits when readonly.
    fireEvent.keyDown(ta, { key: 'Tab' });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('renders the parsed badge only when parsed=true and no error', () => {
    const { rerender } = render(<YamlEditor value="x" parsed />);
    expect(screen.getByTestId('yaml-editor-parsed-badge')).toBeTruthy();
    rerender(<YamlEditor value="x" parsed error="boom" />);
    expect(screen.queryByTestId('yaml-editor-parsed-badge')).toBeNull();
  });
});
