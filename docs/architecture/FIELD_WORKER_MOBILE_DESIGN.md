# Field Worker Mobile Surface — Design Document

Status: DESIGN (not yet implemented)
Owner: Artem (info@datadrivenconstruction.io)
Last revised: 2026-05-24
Target release: v4.8 (pilot) / v5.0 (full role matrix)
Pilot scope: Daily Diary surface only, behind a new `field_worker` role

---

## 1. Problem statement

OCERP is built for desktop-first knowledge workers (estimators, PMs, QSs,
inspectors back at base). Site personnel today either don't use the system
or have to ask an office user to log entries for them. We need a
**field-worker surface** that satisfies four hard constraints:

1. **Simple data entry** — minimal taps; one-thumb operation; voice-input
   compatible (`autocapitalize="sentences"`, large free-text fields, no
   masked inputs that fight the keyboard).
2. **Restricted access** — site workers see ONLY the project(s) they are
   assigned to AND only the modules a foreman has whitelisted. They
   cannot delete, sign, close, or approve anything. A leaked credential
   must not let an attacker pivot to other tenants' data.
3. **Tablet + phone optimised** — thumb-zone-aware layout (primary
   actions in the bottom 33% of the screen), swipe gestures for list
   triage, ≥48×48 px touch targets, single-column forms.
4. **Offline tolerant** — page open in browser, network drops, user keeps
   tapping, syncs when back online. Existing `offlineStore.ts` IndexedDB
   queue (`apiCache` + `mutationQueue`) is the substrate.

The pilot deliberately scopes to **one module surface** (Daily Diary) so
we can ship something credible in 3 dev-days, then expand the role
matrix once we have a real field user shaking the design out.

---

## 2. Inventory of existing pieces

Before designing, we audited what is already in `main` so we reuse, not
duplicate.

### 2.1 Backend RBAC

* `backend/app/core/permissions.py` — central `PermissionRegistry`
  singleton, four canonical roles in `Role` StrEnum: `admin`, `manager`,
  `editor`, `viewer`. `ROLE_HIERARCHY` numeric ranks (`viewer=0 …
  admin=3`) drive role-has-permission.
* `ROLE_ALIASES` accepts industry-flavoured strings (`estimator`,
  `quantity_surveyor`, `qs`, `owner`, `guest`) — all of which collapse
  back to one of the four canonical roles. There is **no
  `field_worker` role today**; adding it is the first action in this
  doc.
* `RequirePermission(perm)` and `RequireRole(role)` in
  `backend/app/dependencies.py:277,344` are the only enforcement
  surfaces. Both read the JWT payload's `role` claim and check the
  registry. A stale-JWT live-registry fallback already exists, so
  changing a role's permissions takes effect immediately without
  forcing logout (good for field rollout).
* Per-module permissions follow the pattern `{module}.{action}`. The
  pilot module `daily_diary` registers 13 permissions
  (`backend/app/modules/daily_diary/permissions.py`), keyed by canonical
  `Role`. HSE Advanced exposes 16; Safety exposes 4.

### 2.2 Buyer portal — magic-link pattern

`backend/app/modules/property_dev/portal_*` ships a magic-link auth
flow for unauthenticated buyers that we mirror closely:

* `PortalLinkService` mints a JWT with `scope='portal'` + `type='portal'`
  + persisted `jti` row (`oe_propdev_portal_token`) for audit and
  revocation. TTL 30 days.
* `verify_token` re-decodes, cross-checks the `jti` is not revoked, the
  `sub` matches the buyer row, the `expires_at` is in the future, then
  stamps `last_used_at` / `last_used_ip` best-effort.
* Every `/buyer/{token}/...` handler runs through `_resolve_portal_context`
  which combines per-token rate limiting (30 req/min via
  `approval_limiter` bucket prefix `propdev_portal:`) with the verify
  step.
* All IDOR mismatches collapse to **404 not 403** so the endpoint
  cannot be turned into an existence oracle.

This is the exact shape we want for the field-worker token. The
differences (see §4) are: the subject is a `User` row not a `Buyer`
row, the `scope` claim is `field`, and the worker authenticates with a
short PIN on top of the magic link to defeat URL-shoulder-surfing.

### 2.3 Mobile-aware frontend — top 5 / bottom 5

We grepped 63 occurrences of `md:` / `sm:` / `lg:` breakpoint usage
across `frontend/src/features/`. Qualitative review:

**Best mobile patterns today**

1. `frontend/src/features/buyer-portal/BuyerPortalPage.tsx` — single
   column, large cards, no AG Grid; carries the magic-link pattern.
2. `frontend/src/features/accommodation/AccommodationListPage.tsx` —
   responsive cards with stacked metadata.
3. `frontend/src/features/contacts/ContactsPage.tsx` — list view collapses
   to single column.
4. `frontend/src/features/property-dev/dashboards/*` — card-grid stacks
   to one column under `md`.
5. `frontend/src/shared/ui/PWAInstallPrompt.tsx` — a true mobile-class
   component (sheet-style, dismissible, iOS-aware).

**Worst — desktop-only, will not render usefully under 768 px**

1. `frontend/src/features/boq/BOQEditorPage.tsx` — AG Grid + hierarchical
   editing, fundamentally a desktop surface.
2. `frontend/src/features/bim/BIMPage.tsx` — Three.js viewer; minimum
   1024 px assumed.
3. `frontend/src/features/cad-explorer/*` — wide multi-pane layout.
4. `frontend/src/features/schedule/SchedulePage.tsx` — Gantt with
   horizontal scroll baked in.
5. `frontend/src/features/match-elements/MatchElementsPage.tsx` — 4-step
   wizard with side-by-side panes.

The field surface deliberately reuses ZERO of these — it ships its own
bottom-nav + card-list layout under a new `/field` route.

### 2.4 PWA setup

`frontend/vite.config.ts` already wires `vite-plugin-pwa` with:

* `registerType: 'autoUpdate'` + `clientsClaim` / `skipWaiting`
* Manifest: name `OpenConstructionERP`, short_name `OCERP`, theme
  `#0284c7`, standalone, 5 SVG icons (192/256/384/512/maskable-512) in
  `frontend/public/pwa/`.
* Workbox runtime caches: `oce-static-assets` (CacheFirst, 30 d),
  `oce-i18n-locales` (StaleWhileRevalidate, 14 d), `oce-api`
  (NetworkFirst, 8 s timeout, 1 d, GETs only).
* `navigateFallback: '/index.html'` + denylist on `/api/`, `/static/`,
  `/pwa/`.

So the PWA app shell is already offline-capable. What the field surface
adds on top:

* Pre-seed `oce-api` with **today's project bundle** at login time
  (one-shot fetch of `/api/v1/field/today/{project_id}`) so the worker
  can open the app, drive to site, lose signal, and still see crew /
  diary / open NCRs.
* Route GETs through `getCachedResponse` fallback when `navigator.onLine
  === false`.
* All POST/PUT writes go through `queueMutation` (already implemented
  in `frontend/src/shared/lib/offlineStore.ts:152`) and replay on the
  `online` event.

### 2.5 Geo + photo capture

Audit: **no module today persists `latitude`, `longitude` or `gps`
columns**. Daily Diary's `DiaryPhoto` model carries the file ref but
not a geotag column (only the EXIF inside the JPEG, which we don't
parse server-side). HSE Advanced models also lack geo columns.

The field surface introduces a thin `field_capture` payload on every
mutation:

```jsonc
{
  "captured_at": "2026-05-24T11:47:03+02:00",
  "lat": 50.0850,           // optional; null if user denied
  "lon": 14.4214,           // optional
  "accuracy_m": 12.5,       // optional
  "device_hint": "Android tablet | PWA"
}
```

…which lands in the existing `metadata_` JSON column on whichever
record the capture creates. **No schema migration needed for the
pilot.** A future R8 sweep can promote these to indexed columns if
geo-search becomes a feature.

---

## 3. Roles

| Role | Canonical fallback | Owns | Typical persona |
|------|--------------------|------|-----------------|
| `field_worker` | new | only own captures | labourer, machine operator |
| `site_foreman` | new | own crew + can sign off worker entries | crew foreman, charge-hand |
| `site_inspector` | new | reads everything project-scoped, writes inspections / NCRs / HSE incidents | QA inspector, HSE officer, building control |
| `project_manager` | alias of `manager` | full project surface | existing PM |
| `admin` | existing | tenant-wide | existing |

The three new roles live alongside the existing four. We register them
as **first-class `Role` enum values** (not aliases) because each one
has a distinct numeric rank in `ROLE_HIERARCHY` and a distinct default
permission profile.

Proposed `ROLE_HIERARCHY` extension:

```
field_worker   -2   # below viewer
site_foreman   -1   # above field_worker, below viewer
site_inspector  0   # equal to viewer (read-broad, write-narrow)
viewer          0   # existing
editor          1   # existing
manager         2   # existing
admin           3   # existing
```

`site_inspector` shares rank 0 with `viewer` because most of its
permissions are read-only; its write power comes from a small
allow-list of `*.create` permissions explicitly granted to its role
profile, not from rank.

`field_worker` ranks below `viewer` because it must NOT inherit
`viewer`'s broad `.read` permissions across all modules. The role
gains read access ONLY to modules it is explicitly granted via the
foreman-controlled module whitelist (see §4.3).

---

## 4. Permission matrix

We deliberately keep this matrix narrow for the pilot — only Daily
Diary actions are exhaustively listed; everything else is a "no" until
a foreman flips it on. Format: `R` = read, `W` = write (create or
update), `D` = delete, `S` = sign/close/approve.

### 4.1 Pilot module: Daily Diary

| Action | field_worker | site_foreman | site_inspector | manager |
|--------|:-:|:-:|:-:|:-:|
| `daily_diary.read` (own crew's diary today) | R (own day only) | R (project) | R (project) | R |
| `daily_diary.read` (any past day) | — | R | R | R |
| `daily_diary.create` (add entry) | W (own entries) | W | W | W |
| `daily_diary.update` (own entries, <24 h) | W | W | W | W |
| `daily_diary.update` (others' entries) | — | W (crew) | — | W |
| `daily_diary.delete` | — | — | — | D |
| `daily_diary.upload_photo` | W | W | W | W |
| `daily_diary.attach_drone` | — | W | — | W |
| `daily_diary.attach_reality_capture` | — | — | — | W |
| `daily_diary.close` | — | S | — | S |
| `daily_diary.sign` | — | — | — | S |
| `daily_diary.unlock` | — | — | — | S |
| `daily_diary.archive` | — | — | — | S |
| `daily_diary.export_scl_bundle` | — | — | — | S |
| `daily_diary.fetch_weather` | W (auto) | W | W | W |

### 4.2 Phase-2 modules (post-pilot, design only)

For each role, list the action verb the role can do; "—" means denied.

| Module | field_worker | site_foreman | site_inspector |
|--------|--------------|--------------|----------------|
| `hse_advanced` | report incident, upload photo | + activate permit, update prereqs | + close investigation, conduct audit |
| `safety` | report toolbox-talk attendance | + create record | + create + close |
| `inspections` | — | — | create, complete |
| `ncr` | flag (creates draft) | — | create, attach evidence |
| `punchlist` | mark done (own items) | reassign within crew | create item, verify |
| `daily_diary` | (above) | (above) | (above) |
| `field_reports` | create | + close | + close |
| `equipment` | log usage hours | + downtime | — |
| `documents` | read tagged-`field` only | read project | read project |
| `rfi` | — | flag question | — |
| `submittals` | — | — | — |
| `boq`/`costs`/`estimating` | — | — | — |
| `finance` | — | — | — |

Everything not listed: **denied by default**. The matrix only widens
through an explicit foreman action.

### 4.3 Per-project + per-module scope guards

RBAC alone is not enough — `field_worker` Alice on Project A must not
read `daily_diary` on Project B even if she technically has
`daily_diary.read`. Two guards combine:

1. **Project membership** — extend the existing `User.project_ids`
   association (or its equivalent in the users module) so every
   non-admin call is filtered `WHERE project_id IN (:caller_project_ids)`.
   For field roles this is enforced at the **service layer**, not the
   router, so the existing `RequirePermission` dep stays clean.
2. **Foreman-controlled module whitelist** — a new table
   `oe_field_module_grant(user_id, project_id, module_name,
   granted_by, granted_at, revoked_at)`. A `site_foreman` provisions
   a worker by granting them `daily_diary` on Project A. The
   permission engine's effective check for a field role becomes:

   ```
   permission_registry.role_has_permission(role, perm)
     AND project_id ∈ caller.project_ids
     AND module_of(perm) ∈ active_field_grants(caller, project_id)
   ```

   The whitelist is the kill-switch — a foreman revokes a fired
   worker's access in one tap without touching the role.

### 4.4 IDOR / cross-tenant guard

Field endpoints follow the buyer-portal convention: every mismatch
between request UUID and caller scope collapses to **404 not 403**.
This already exists for `property_dev`; we mirror the pattern for the
new `/api/v1/field/*` routes.

---

## 5. Auth flow — three options

### Option A — SMS magic link (mirrors buyer portal)

* Foreman taps "Issue worker link" → backend mints a JWT
  (`scope='field'`, TTL 30 d), SMS-sends URL `/field/{token}`.
* Worker opens URL in tablet browser → app caches token in
  IndexedDB → bottom-nav shell renders.

**Pro** — zero credentials to remember; mirrors a pattern we already
ship.
**Con** — requires SMS gateway (Twilio etc.) before pilot; cost per
worker; SIM-less site tablets can't receive.

### Option B — PIN per worker (foreman provisions)

* Foreman creates worker row → assigns 6-digit PIN displayed once.
* Worker enters PIN on a shared `/field` login → backend issues
  JWT.
* PIN can be rotated; 5 wrong tries = lock for 15 min.

**Pro** — works offline-first (you can pre-issue PINs and laminate
them); no telecom dep; shared tablet OK.
**Con** — PINs get shared / written on the hard hat; revocation needs
both PIN change AND token revoke.

### Option C — QR badge

* Worker has a QR code on their ID badge / hard hat sticker.
* Tablet's camera scans → URL = magic-link → same flow as A.

**Pro** — sub-second sign-in; physical badge = physical security
boundary.
**Con** — needs camera permission + the QR generator + a print
pipeline; loses the device-camera permission once and the worker is
locked out until reissue.

### Recommendation

**Pilot: Option B (PIN), wrap it as a magic-link.** A `site_foreman`
issues a worker an `/field/{token}` URL (single tap from the foreman
UI), the worker bookmarks it once, and a 6-digit PIN gates the JWT
issuance.

* The bookmarked URL is **only** half a credential — useless without
  the PIN.
* The PIN is **only** half a credential — useless without knowing the
  bookmarked URL (which carries an opaque token id, not a username).
* Stolen tablet → foreman taps "revoke" → both halves dead.

This gives us 2-of-2 from two trivially different channels (paper
laminate vs. browser bookmark) with zero telecom dependency and no
camera-permission cliff. SMS (Option A) and QR (Option C) ship as
optional alternative provisioning flows in v5.0.

---

## 6. UI patterns

### 6.1 Shell

* **Bottom nav, four items max**:
  `My Today` · `Capture` · `Crew` · `Profile`
* Tab bar height 64 px; icons 28 px; label 11 px below icon; safe-area
  inset on iOS via `env(safe-area-inset-bottom)`.
* No top nav. Header is a 56 px sticky band with current project name
  + a single 44×44 "?" button for help.
* Sidebar from the existing desktop shell is **never mounted** on
  `/field/*` routes. We render a separate `FieldShellPage` instead of
  `AppLayout`.

### 6.2 Capture flow (3 screens)

```
┌──────── Screen 1 ────────┐   ┌──────── Screen 2 ────────┐   ┌──────── Screen 3 ────────┐
│ [Camera viewfinder]      │   │ What is this?             │   │ Add a note (optional)    │
│                           │   │ ┌──────────────┐           │   │ ┌──────────────────────┐ │
│                           │   │ │ HSE Incident │           │   │ │                      │ │
│                           │   │ ├──────────────┤           │   │ │  voice input ready   │ │
│                           │   │ │ Progress     │           │   │ │                      │ │
│ [O] big shutter button   │   │ ├──────────────┤           │   │ └──────────────────────┘ │
│                           │   │ │ Defect / NCR │           │   │ Location auto-tagged ✓   │
│ [picker] [flip] [flash]   │   │ ├──────────────┤           │   │ [ Submit (1 photo + GPS)]│
└──────────────────────────┘   │ │ Toolbox talk │           │   └──────────────────────────┘
                                │ └──────────────┘           │
                                └──────────────────────────┘
```

Touch targets: each category tile is 88×88 (well above the 48 min).
Submit button spans full width at the bottom, 56 px tall.

### 6.3 Forms

* Single column. Label above input, never beside.
* Inputs full-width, 48 px tall, 16 px font (iOS won't zoom).
* Errors inline directly below the input, red-500 text, 14 px.
* No masked inputs. Phone numbers use `inputmode="tel"`,
  dates `type="date"` (native picker).
* Voice friendly: `autocapitalize="sentences"`, `spellcheck="true"`,
  `enterkeyhint="next"` between fields, `enterkeyhint="send"` on the
  final field.

### 6.4 Touch targets

≥48×48 minimum (matches WCAG 2.2 SC 2.5.8 AAA + Apple HIG +
Material 3). Validated automatically by the QA crawler skill via the
existing axe-core integration.

### 6.5 Dark mode

**Auto, light-default.** Outdoor sun glare argues for HIGH-CONTRAST
white, not dark. Most published research on outdoor screen
legibility (Apple's own iOS Auto-Brightness rationale, Sony Xperia
"Sunlight Mode") inverts to bright-white for outdoor use, not dark.
The user can toggle in Profile if they prefer dark. Respects
`prefers-color-scheme` for any worker who pinned the OS to dark.

---

## 7. Offline strategy

The substrate already exists; the field surface adds a thin
orchestration layer.

### 7.1 Reads — service worker NetworkFirst + IndexedDB fallback

* App shell precached by workbox (existing).
* Today's project data pre-seeded at login: one `GET
  /api/v1/field/today/{project_id}` returns crew, today's diary
  header, open NCRs, open punchlist items, weather. Response cached
  in `oce-api` AND mirrored into `oe_offline.apiCache` with a 24 h
  TTL.
* All other GETs use the existing `getCachedResponse(path)` fallback
  when `navigator.onLine === false`.

### 7.2 Writes — IndexedDB queue + online-event replay

* All POST/PUT/PATCH go through a new `submitFieldMutation(path,
  body)` helper:
  * If online → fetch directly, return result.
  * If offline → `queueMutation({method, path, body, queuedAt,
    retries: 0})` → return optimistic local placeholder.
* `window.addEventListener('online', replayQueue)` drains FIFO.
* Replay batches max 5 in parallel to avoid hammering a recovering
  link.

### 7.3 Conflict resolution

* **Server wins**. A queued mutation that returns 409 is moved to a
  `failedMutations` store, surfaces as a toast ("Your entry
  conflicts with a more recent one — tap to review") and lets the
  worker either keep their local copy as a new entry or discard.
* Retry policy: exponential backoff (1 s, 5 s, 30 s, 5 m, 30 m,
  give up). After give-up the row stays in `failedMutations`
  forever until the worker dismisses it; never silently dropped.

### 7.4 Photos

Photos are the heavy payload. The pilot uses the existing
`upload_photo` endpoint but with two field-only changes:

* Resize client-side to max 1600 px long edge BEFORE queueing.
  Cuts payload ~10x; OK for evidence quality.
* Store the original blob in a separate IndexedDB object store
  (`fieldPhotos`) keyed by mutation id. Drained on `online` event.

---

## 8. Wireframes

### 8.1 My Today

```
┌─ Project North Site · Tue 24 May ─────────?─┐
│                                              │
│ Today's diary · Open                         │
│ ┌──────────────────────────────────────────┐ │
│ │ Weather   ☀ 18°C  wind 12 km/h           │ │
│ │ Crew      14 on site                     │ │
│ │ My entries  2 (1 pending sync ⤴)        │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ Quick actions                                │
│ ┌──────┬──────┬──────┐                       │
│ │ +    │ HSE  │ NCR  │                       │
│ │ Note │ Inc. │      │                       │
│ └──────┴──────┴──────┘                       │
│                                              │
│ Today's open punchlist (3)                   │
│ • Door 3-B – seal missing                    │
│ • Wall 4-A – touch-up paint                  │
│ • Stairs L2 – nosing strip                   │
│                                              │
├────[ Today ][ +Capture ][ Crew ][ Me ]──────┤
└──────────────────────────────────────────────┘
```

### 8.2 Capture · Screen 1 (camera)

```
┌──────────────────────────────────────────────┐
│ ✕ Cancel                            Skip ⤳   │
│                                              │
│         [ live camera viewfinder ]           │
│                                              │
│                                              │
│                                              │
│              (   ⬤  shutter   )              │
│                                              │
│   ⇧Gallery     ↻Flip      ⚡Flash            │
├────[ Today ][ +Capture ][ Crew ][ Me ]──────┤
└──────────────────────────────────────────────┘
```

### 8.3 Capture · Screen 2 (categorise)

```
┌──────────────────────────────────────────────┐
│ ← Back                                       │
│ What did you capture?                        │
│                                              │
│ ┌────────────┐ ┌────────────┐                │
│ │ ⚠ HSE      │ │ ✓ Progress │                │
│ │  incident  │ │            │                │
│ └────────────┘ └────────────┘                │
│ ┌────────────┐ ┌────────────┐                │
│ │ ✗ Defect / │ │ 🛡 Toolbox │                │
│ │   NCR      │ │   talk     │                │
│ └────────────┘ └────────────┘                │
│ ┌────────────┐                               │
│ │ 📝 General │                               │
│ │   note     │                               │
│ └────────────┘                               │
└──────────────────────────────────────────────┘
```

### 8.4 Capture · Screen 3 (comment + submit)

```
┌──────────────────────────────────────────────┐
│ ← Back                                       │
│ Add details (optional)                       │
│                                              │
│ ┌──────────────────────────────────────────┐ │
│ │                                          │ │
│ │ Tap to type — or 🎙 hold for voice       │ │
│ │                                          │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ Tagged automatically                         │
│  ⏱ 11:47 · 📍 50.085 N, 14.421 E (±12 m)    │
│  📷 1 photo (1.2 MB)                         │
│                                              │
│                                              │
├──────────────────────────────────────────────┤
│ [        Submit · queued if offline       ] │
└──────────────────────────────────────────────┘
```

### 8.5 HSE incident report (full form)

```
┌──────────────────────────────────────────────┐
│ ← Back                                       │
│ Report HSE incident                          │
│                                              │
│ Severity                                     │
│ ( ) Minor   (•) First aid                    │
│ ( ) Lost-time  ( ) Critical                  │
│                                              │
│ What happened                                │
│ ┌──────────────────────────────────────────┐ │
│ │ Worker slipped on wet floor near …       │ │
│ └──────────────────────────────────────────┘ │
│                                              │
│ Who was involved (tap to add)                │
│ [ + add person ]   <-- searches own crew     │
│                                              │
│ Photos (1)                                   │
│ [ thumb ] [ + ]                              │
│                                              │
│ ✓ Notify foreman immediately                 │
│                                              │
├──────────────────────────────────────────────┤
│ [             Submit incident             ] │
└──────────────────────────────────────────────┘
```

### 8.6 Time / progress entry

```
┌──────────────────────────────────────────────┐
│ Time entry · Tue 24 May                      │
│                                              │
│ Trade  [ Carpenter      ▾ ]                  │
│ Crew   [ My crew (4)    ▾ ]                  │
│ Hours  [    8.0    ]   ▼ + ▲                 │
│ Activity                                     │
│ [ Form-work to slab 4 ▾ ]                    │
│                                              │
│ Notes (optional, voice friendly)             │
│ ┌──────────────────────────────────────────┐ │
│ │                                          │ │
│ └──────────────────────────────────────────┘ │
│                                              │
├──────────────────────────────────────────────┤
│ [               Log entry                 ] │
└──────────────────────────────────────────────┘
```

---

## 9. Pilot scope (3-day build)

### Day 1 — backend role + scope filter

* Extend `Role` enum with `FIELD_WORKER`, `SITE_FOREMAN`,
  `SITE_INSPECTOR`. Add `ROLE_HIERARCHY` ranks and aliases.
* Add `register_field_role_permissions()` that registers Daily-Diary
  permissions for the three roles per the matrix in §4.1.
* Add `oe_field_module_grant` Alembic migration (single new table —
  no FK to module rows because modules are not DB-backed).
* Add `field_scope.py` helper: `scope_query(stmt, caller_payload)`
  that injects `WHERE project_id IN :caller.project_ids` for
  field-role callers, no-op for manager+.

### Day 2 — `/api/v1/field/*` router

* `POST /field/auth/redeem-pin` — exchange `{token, pin}` for a
  short-lived (8 h) `scope='field'` JWT. Token TTL stays 30 d as a
  long-lived **issuance** capability; the access JWT is short-lived.
* `GET /field/today/{project_id}` — single-round-trip payload for the
  Today screen.
* `POST /field/capture/photo` — multi-part upload with `category`,
  `lat`/`lon`/`accuracy`, optional `note`. Magic-byte validated
  (`jpeg|png|heic|heif`) reusing `app.core.file_signature`.
* `GET /field/crew/{project_id}` — names + status of caller's crew.
* All endpoints behind `RequirePermission` + new
  `RequireFieldScope(module_name)` dep that checks
  `oe_field_module_grant`.

### Day 3 — frontend `/field` shell

* New `FieldShellPage` (bottom nav, no sidebar) at `/field`.
* Lazy-loaded route in `App.tsx` — separate chunk; no impact on
  existing desktop bundle size.
* Three placeholder routes for Today / Capture / Crew, plus a Profile
  page that surfaces "switch project", "PIN change", "sign out".
* Wire `submitFieldMutation` helper to `offlineStore`.
* PIN entry screen on `/field/{token}` mounting if URL has token.

### Out of scope for pilot (deferred to v5.0)

* HSE / NCR / inspections capture (only generic photo capture in
  pilot).
* Crew time tracking (pilot reads crew, doesn't write hours).
* Foreman sign-off UI on worker entries.
* SMS magic-link delivery.
* QR-badge provisioning.
* PWA push notifications.

---

## 10. Test plan

* Backend unit tests for `Role` extension and
  `RequireFieldScope` (mock module-grant rows, assert 404 on
  cross-project leak).
* Backend integration test: foreman issues token → worker
  redeems PIN → worker GETs `/field/today/{project_a}` succeeds
  → worker GETs `/field/today/{project_b}` returns 404.
* Frontend Playwright: open `/field/{token}` → enter PIN →
  bottom nav renders → axe-core 0 blocking.
* Offline flow: install PWA, go offline, submit capture, come back
  online, mutation drains, server row appears.

---

## 11. Risks and open questions

| # | Risk / question | Mitigation / next step |
|---|-----------------|------------------------|
| 1 | We have no SMS gateway today; Option A is a v5.0 lift. | Pilot uses Option B (PIN). |
| 2 | `Role` enum change touches every JWT-issuance path. | Land role addition in its own commit before pilot router; existing roles unaffected (we only ADD, never reorder ranks). |
| 3 | `field_worker` rank `-2` may break code that assumes `viewer=0` is the floor. | Grep audit: `ROLE_HIERARCHY.get(... -1)`. Default fallback `-1` would incorrectly grant field workers access. Switch defaults to `-99` in the same commit. |
| 4 | Geo capture without a schema column means we cannot index/search by location. | Acceptable for pilot; v5.0 promotes lat/lon/accuracy_m to first-class indexed columns. |
| 5 | Foreman-controlled module whitelist is a NEW table that must respect tenant deletion. | Cascade `oe_field_module_grant.project_id` ON DELETE CASCADE, matches existing `daily_diary` table family. |
| 6 | Photo retention — workers may queue 50 photos offline that drain at end-of-day. | Cap `fieldPhotos` IndexedDB store at 200 MB; oldest dropped with toast warning. |
| 7 | PIN brute force on a stolen tablet. | 5 wrong PINs → 15-min lockout (backend rate-limit bucket keyed on token id). Audit row written on each attempt. |
| 8 | Site Wi-Fi captive portals interfere with `navigator.onLine`. | `onlineStatus` hook already exists; add a periodic 1-px image fetch fallback against own domain to detect "captive-portal-online-but-not-really". |
| 9 | Workers may share a tablet across shifts. | Profile screen has a 1-tap "Sign out + clear queue" that flushes both the JWT and any unsynced mutations. The next worker re-redeems their own PIN. |
| 10 | Compliance (RIDDOR, OSHA, ISO 45001) requires immutable audit on HSE captures. | Phase-2 only; pilot captures generic photos, no HSE-specific endpoints. |

---

## 12. References to in-repo prior art

* `backend/app/core/permissions.py` — `Role`, `ROLE_HIERARCHY`,
  `PermissionRegistry`
* `backend/app/modules/property_dev/portal_service.py` — magic-link
  JWT pattern (`scope`, `jti`, revocation table)
* `backend/app/modules/property_dev/portal_router.py` — 404-not-403
  IDOR convention, per-token rate limiting
* `backend/app/modules/daily_diary/permissions.py` — full pilot
  module's permission set
* `backend/app/dependencies.py` — `RequirePermission`, `RequireRole`,
  stale-JWT live-registry fallback
* `frontend/vite.config.ts` — workbox runtime caches, PWA manifest
* `frontend/src/shared/lib/offlineStore.ts` — IndexedDB cache +
  mutation queue
* `frontend/src/shared/ui/OfflineBanner.tsx`,
  `frontend/src/shared/ui/PWAInstallPrompt.tsx` — existing offline /
  install-prompt UX

Questions or scope changes: email info@datadrivenconstruction.io.
