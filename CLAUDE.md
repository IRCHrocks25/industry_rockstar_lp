# CLAUDE.md — Working agreement for this repo

Read this and `architecture.md` at the start of every session.
`architecture.md` is the **living source of truth** — if a decision changes,
update it **in the same commit** as the code change.

## What this is

Single-client CMS: import GoHighLevel HTML → OpenAI annotates it **once at
import** (JSON metadata only — the LLM never writes HTML and is never on the
edit/render path) → non-technical team edits via labeled fields + live preview
→ published near-static to `{subdomain}.BASE_DOMAIN`. Funnels = a `Site` with
sibling `Page`s (LP → thank-you) wired through the `/_submit/{form_id}` proxy.

## Stack

Django 5.2 · PostgreSQL 16 (JSONB) · Django-Q2 on the **ORM broker** (no Redis
in v1) · lxml/bs4 (Phase 1+) · OpenAI structured outputs (Phase 3 only) ·
Caddy TLS (`deploy/Caddyfile`) · R2/S3 via django-storages (Phase 1+).

## Phase plan (architecture.md §16) — build ONE phase at a time, app stays runnable + migratable

- ✅ **Phase 0** — foundation: scaffold, settings, custom User, Site/Domain,
  HostRouterMiddleware, placeholder on subdomain, design system, Caddyfile.
- ⬜ **Phase 1** — core loop WITHOUT AI: import → rehost assets → manual
  annotation → edit → publish → serve.
- ⬜ **Phase 2** — funnels & forms: `/_submit` proxy, `Submission` ledger,
  async webhook retry, thank-you wiring.
- ⬜ **Phase 3** — LLM annotation (skeleton → OpenAI → materialize, review UI).
- ⬜ **Phase 4** — countdowns (`CountdownConfig` + `countdown.js` + editor).
- ⬜ **Phase 5** — polish: history/rollback UI, custom domains, managed
  scripts, lead dashboards.
- ⬜ **Phase 6** — advanced: re-import diff-merge, global blocks, A/B, GHL API.

## Decisions already made (do not re-litigate; architecture.md §13)

1. `Submission` ledger ships in v1 (payload + webhook status/attempts; no UI).
2. `gate_redirect_on_success` defaults to **false** (resilient: store, 302
   immediately, forward async with retries). Per-form toggle.
3. Custom domains are v2; v1 = subdomains only (Domain model exists now).
4. Django-Q2 ORM broker; add Redis only when caching needs it.

## Conventions

- Apps live under `apps/` (`apps.sites`, …); settings in `config/settings.py`,
  per-plane urlconfs in `config/urls_control.py` / `config/urls_publishing.py`.
- **UUID pks** on domain models. `AUTH_USER_MODEL = accounts.User` (has `role`).
- Secrets only in `.env` via django-environ (`.env.example` is the contract;
  never commit `.env`).
- Host routing: `HostRouterMiddleware` sets `request.urlconf` (+ `request.site`
  on the publishing plane); unknown hosts 404. Session/CSRF cookies are
  host-only on APP_HOST — never `Domain=.BASE_DOMAIN`.
- Small, reviewable commits; explain what/why after each step. Ask before any
  dependency or structural decision the doc doesn't cover.
- Tests (Django test runner, `manage.py test apps`) for non-trivial logic:
  routing, annotation materialize, render/patch, submit proxy + retry. Skip
  trivial glue.
- Dev commands: `scripts/dev.ps1 <task>` on Windows, `make <task>` elsewhere —
  run / worker / migrate / test / setup (+ `db-install|db-init|db-start` for
  the portable Postgres in `.pg/` when Docker is absent).
- Dev hosts: control plane `app.localhost:8000`, published sites
  `{sub}.localhost:8000`.

## Design (see DESIGN.md — binding)

Light UI only. **Never purple/violet/indigo.** No gradient heroes,
glassmorphism, emoji-as-icons, shadow piles, or centered-template app screens.
True-gray neutrals + forest-green accent (#166534), IBM Plex Sans/Mono,
4px spacing scale, hairline borders, Lucide icons via `static/icons.svg`,
visible focus rings, WCAG AA. Build new UI from `tokens.css` + `app.css`
components — extend the system, don't improvise per-screen. The end user is a
non-technical marketer: plain-language labels, one obvious primary action per
screen.
