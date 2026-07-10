# Landing Page Platform

A single-client CMS that turns GoHighLevel-exported HTML into editable,
subdomain-hosted landing pages and multi-page funnels, with first-class
countdown timers. See [architecture.md](architecture.md) — the source of truth —
and [CLAUDE.md](CLAUDE.md) for working conventions.

**Core principle:** OpenAI annotates imported HTML **once, at import time**, and
only returns JSON metadata. It never writes markup and is never on the edit or
render path.

## Stack

Django 5 · PostgreSQL · Django-Q2 (ORM broker) · lxml/BeautifulSoup ·
Caddy (TLS) · Cloudflare R2/CDN · OpenAI (annotation only)

## Quickstart (dev)

Requires Python 3.11+ and a PostgreSQL 16 reachable at `DATABASE_URL`.

```
# 1. Postgres — pick one:
docker compose up -d db                       # if you have Docker
powershell -File scripts\dev.ps1 db-install   # no Docker: portable Postgres
powershell -File scripts\dev.ps1 db-init      #   into gitignored .pg/
powershell -File scripts\dev.ps1 db-start

# 2. App (Windows; on unix use `make <target>` with the same names):
powershell -File scripts\dev.ps1 setup
powershell -File scripts\dev.ps1 migrate
powershell -File scripts\dev.ps1 superuser
powershell -File scripts\dev.ps1 run          # web, http://app.localhost:8000
powershell -File scripts\dev.ps1 worker       # Django-Q2 qcluster (2nd terminal)
powershell -File scripts\dev.ps1 test
```

Secrets live in `.env` (copied from `.env.example` by `setup`), never committed.

## Hosts in dev

`*.localhost` resolves to `127.0.0.1` in modern browsers — no hosts-file edits:

- `http://app.localhost:8000` — control plane (editor/admin, auth required)
- `http://{subdomain}.localhost:8000` — published site for that `Site`
- unknown subdomains → 404

## Deploy

Production sits behind Caddy (wildcard TLS for `*.yourdomain.com`); see
`deploy/Caddyfile`. Wildcard DNS `*.yourdomain.com` → the app host. Custom
domains are v2 (on-demand TLS is stubbed in the Caddyfile).
