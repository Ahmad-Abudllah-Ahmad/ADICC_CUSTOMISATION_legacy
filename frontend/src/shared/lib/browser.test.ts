/**
 * Regression guard for the secure-context helpers.
 *
 * The bug: on a self-hosted instance reached over plain http://<server-ip>
 * (not localhost, not https) the page is not a "secure context", so
 * `crypto.randomUUID` and `navigator.clipboard` are undefined and calling them
 * throws ("crypto.randomUUID is not a function"), which broke the DWG upload
 * and every other id/copy path. These tests simulate that environment and pin
 * that the helpers never throw and still return a valid v4 UUID.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';

import { copyToClipboard, readClipboard, uuid } from './browser';

const V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('uuid()', () => {
  it('uses crypto.randomUUID when present', () => {
    const fake = '11111111-2222-4333-8444-555555555555';
    vi.stubGlobal('crypto', { randomUUID: () => fake });
    expect(uuid()).toBe(fake);
  });

  it('falls back to getRandomValues when randomUUID is missing (insecure context)', () => {
    // Real non-secure context: crypto exists, getRandomValues works,
    // randomUUID/subtle are gone.
    vi.stubGlobal('crypto', {
      getRandomValues: (arr: Uint8Array) => {
        for (let i = 0; i < arr.length; i += 1) arr[i] = (i * 37 + 7) & 0xff;
        return arr;
      },
    });
    const id = uuid();
    expect(id).toMatch(V4);
  });

  it('falls back to Math.random when crypto is entirely absent', () => {
    vi.stubGlobal('crypto', undefined);
    const id = uuid();
    expect(id).toMatch(V4);
  });

  it('produces distinct ids', () => {
    vi.stubGlobal('crypto', {
      getRandomValues: (arr: Uint8Array) => {
        for (let i = 0; i < arr.length; i += 1) arr[i] = Math.floor(Math.random() * 256);
        return arr;
      },
    });
    const ids = new Set(Array.from({ length: 200 }, () => uuid()));
    expect(ids.size).toBe(200);
  });
});

describe('copyToClipboard()', () => {
  it('uses navigator.clipboard.writeText when available', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const ok = await copyToClipboard('hello');
    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalledWith('hello');
  });

  it('does not throw when navigator.clipboard is undefined (insecure context)', async () => {
    vi.stubGlobal('navigator', {});
    // execCommand path: jsdom has no real clipboard, so this resolves false
    // without throwing - which is the contract callers rely on.
    await expect(copyToClipboard('x')).resolves.toBeTypeOf('boolean');
  });
});

describe('readClipboard()', () => {
  it('returns "" when navigator.clipboard is undefined', async () => {
    vi.stubGlobal('navigator', {});
    await expect(readClipboard()).resolves.toBe('');
  });

  it('reads via the API when available', async () => {
    vi.stubGlobal('navigator', { clipboard: { readText: () => Promise.resolve('pasted') } });
    await expect(readClipboard()).resolves.toBe('pasted');
  });
});
