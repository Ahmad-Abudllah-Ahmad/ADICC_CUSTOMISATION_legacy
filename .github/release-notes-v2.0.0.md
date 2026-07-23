# OpenConstructionERP v2.0.0 — Second stable release

The second major stable release. Supersedes the entire 1.x line and
establishes the platform baseline going forward.

`pip install --upgrade openconstructionerp`

## 🔧 Reliability

- **AI Chat SSE streams** survive middleware cancellation (asyncio.shield on DB flush)
- **AI API keys** survive backend restarts — absolute-path `.env` loading, Fernet decryption gating
- **DWG Takeoff** respects DXF `$INSUNITS` end-to-end (canvas, popover, BOQ link)
- **BIM Linked-BOQ panel** populates via new aggregate endpoint — 3,897 real DB links render instead of a blank panel
- **BIM Rules** deep-links to `?mode=requirements`
- **CDE containers**: trailing-slash route fix, no more 307 auth drop
- **AI Estimate Save-as-BOQ**: trailing-slash route fix
- **Cost Intelligence Advisor** renders safe markdown subset (bold/italic/headings/lists)
- **Modal backdrops** now properly cover the sticky header (z-index rebalance)

## 📊 CAD-BIM BI Explorer

*Renamed from CAD-BIM Explorer.*

- **KPI dashboard strip**: Elements · Volume · Area · Length · Weight · Categories · Levels
- **Power-BI-style data bars** in pivot cells — magnitudes readable at a glance
- Slicers, saved views, drill-down from charts

## 🧩 Module Developer Experience

- `MODULES.md` at repo root — single entry point for module builders
- New in-app `/modules/developer-guide` React page (steps, code blocks, install guide, quick-reference table)
- Prominent **"+ Add module"** CTA at the bottom of the sidebar

## ✨ UX Polish

- Dashboard: Quick Start is pure-navigation, explicit *New Estimate* button, Quality Score icon + click-through to `/validation`
- About page: Artem Boiko avatar, DDC logo, GitHub repo cards, full-width clickable book banner, Community block (LinkedIn / Telegram / X)
- `/projects`: file-type badges right-aligned, md size
- BOQ list: per-row file-type chips
- BOQ grid: PDF-origin icon deep-links to source page
- Markups dropdown no longer clipped; floating AI Chat bubble removed

## 🛡 Security / Provenance

- Layered DDC authorship markers — HTML `<meta>` tags, CSS custom properties on `<html>`, opaque `_ff_build_hash` localStorage key, `X-DDC-Origin` / `X-DDC-Author` / `X-DDC-License` response headers, console banner

## 🧪 Tests

- Fixed 48 backend integration-test failures. Shared fixtures now call `promote_to_admin(email)` after registration (security hardening demotes self-registered users to `viewer`); trailing-slash drift corrected across I18n, Notifications, RFI, Finance, Contacts, Global-search. **61/61 green** end-to-end.
- New Playwright visual-verify spec: **3/3 green** (dashboard, sidebar, About).

## 🧹 Cleanup

- Removed 5 archived duplicate demo projects; 6 regional demos remain
- Removed diagnostic specs, one-off seed scripts, build artifacts
- `.gitignore` tightened for `agent worktrees`, `tsconfig.tsbuildinfo`, etc.
- `ruff --fix` pass over `backend/app/` — 29 fixes across 29 files

## 📚 Full changelog

See [CHANGELOG.md](https://adicc-uae.com/blob/main/CHANGELOG.md#200--2026-04-20).

## 💾 Install

```bash
pip install openconstructionerp==2.0.0
```

or

```bash
git clone https://adicc-uae.com.git
cd OpenConstructionERP
docker compose up -d
```

## 🙏 Feedback

- [LinkedIn](https://www.linkedin.com/company/78381569)
- [Telegram](https://t.me/datadrivenconstruction)
- [X](https://x.com/datadrivenconst)
