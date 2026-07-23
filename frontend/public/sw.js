/**
 * Self-destruct service worker (2026-05-25).
 *
 * Replaces an older workbox-generated SW that was shipped with one of
 * the prod builds and is still registered in user browsers. The stale
 * SW intercepts ``/assets/index-<hash>.js`` requests and serves a
 * frozen prod bundle from cache, even when the dev server runs on the
 * same origin — so every recent fix (dashboard consolidation, catalog
 * tooltip, Operations snapshot, money hardening) was invisible.
 *
 * When the browser's update check pulls this file, it (a) skips its
 * own waiting phase, (b) deletes every cache key it created, (c)
 * unregisters itself, and (d) reloads every controlled tab. After
 * that, ``navigator.serviceWorker.getRegistrations()`` returns an
 * empty list and ``/assets/*`` requests hit the network as intended.
 *
 * This file should remain in place for at least one release cycle so
 * any user who hasn't reopened the app since the bad SW shipped also
 * gets cleaned up. Safe to delete after that.
 */

self.addEventListener('install', () => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
      const regs = await self.registration ? [self.registration] : [];
      await Promise.all(regs.map((r) => r.unregister()));
      const clients = await self.clients.matchAll({ type: 'window' });
      clients.forEach((c) => c.navigate(c.url));
    })(),
  );
});
