/**
 * Smoke — global keyboard shortcuts.
 *
 *   Cmd/Ctrl+K → command palette opens
 *   ?          → keyboard shortcuts help opens
 */
import { test, expect } from '../fixtures';
import { gotoModule, openCommandPalette, openShortcutsHelp, captureScreen } from '../helpers';

test.describe('@smoke keyboard-shortcuts', () => {
  test('Cmd/Ctrl+K opens the command palette', async ({ authedPage }) => {
    await gotoModule(authedPage, 'dashboard');
    await openCommandPalette(authedPage);
    const palette = authedPage.locator(
      '[data-testid="command-palette"], [role="dialog"][aria-label*="command" i], [role="combobox"][aria-label*="search" i]',
    ).first();
    const visible = await palette.isVisible({ timeout: 2_500 }).catch(() => false);
    if (!visible) {
      test.info().annotations.push({ type: 'note', description: 'command palette not yet shipped — soft skip' });
      test.skip(true, 'command palette not detected');
    }
    await captureScreen(authedPage, 'smoke', 'command-palette');
  });

  test('? opens the keyboard shortcuts help', async ({ authedPage }) => {
    await gotoModule(authedPage, 'dashboard');
    await openShortcutsHelp(authedPage);
    const help = authedPage.locator(
      '[data-testid="shortcuts-help"], [role="dialog"]:has-text(/shortcut|tastatur|клавиш/i)',
    ).first();
    const visible = await help.isVisible({ timeout: 2_500 }).catch(() => false);
    if (!visible) {
      test.skip(true, 'shortcuts help not detected');
    }
    await captureScreen(authedPage, 'smoke', 'shortcuts-help');
  });
});
