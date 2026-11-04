# Plytos

**Play to your strengths.** Plytos is a candidate-owned vault of evidence-backed
strength cards. People build each card once, keep its history for their whole
career, and recombine cards for each application.

- Product spec: [Plytos v1 candidate experience](https://claude.ai/artifact/FgjGX7dgMcExXqs6fmj2cy)
- Data model and versioning rules: [docs/data-model.md](docs/data-model.md)
- Instructions for AI coding agents: [CLAUDE.md](CLAUDE.md)

## What's here

| Path | What it is |
| --- | --- |
| `apps/web` | Next.js web app, mobile first, installable on phones. The only public entry point |
| `services/api` | Python API (FastAPI, Postgres). Private: only the web app's server calls it |
| `services/api/migrations` | The Postgres schema, as plain SQL applied in order |
| `infra/terraform` | Google Cloud setup: Cloud Run, Cloud SQL, KMS, Storage, deploy identity |
| `.github/workflows` | CI (secret scan, tests, builds, Terraform checks) and a manual deploy |

## Run it locally

You need Docker (or any Postgres 16), Node 22 and [uv](https://docs.astral.sh/uv/).

```sh
docker compose up -d db

# API: create the schema, then serve on :8000 as a dev user
cd services/api
uv sync --all-extras
PLYTOS_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres \
  uv run python -m plytos_api.migrate
psql postgresql://postgres:postgres@localhost:5432/postgres \
  -c "create role plytos_dev login password 'dev' in role plytos_app"
PLYTOS_ENV=dev \
PLYTOS_DATABASE_URL=postgresql://plytos_dev:dev@localhost:5432/postgres \
PLYTOS_KEK="local:$(openssl rand -base64 32)" \
  uv run uvicorn --factory plytos_api.main:create_app --reload --port 8000

# Web app on :3000, signed in as the same dev user
cd apps/web
npm install
PLYTOS_ENV=dev PLYTOS_DEV_USER=me PLYTOS_API_URL=http://localhost:8000 npm run dev
```

The API connects as a non-owner role on purpose: row-level security only
applies to roles that don't own the tables. A dev KEK is regenerated each run
above, so restart with the same value if you want to keep reading old cards.

Tests: `uv run pytest` in `services/api` (uses the same Postgres, in a
throwaway database) and `npm test` in `apps/web`.

## Status

This is milestone M0, Foundations. Built so far:

- The card schema: main lines for facts, variant lines for framing, numbered
  append-only versions with a hash chain, targets, and an event log.
- Privacy controls: row-level security per person, per-person data keys
  wrapped by Cloud KMS, `noindex` everywhere, no public API.
- Infrastructure as code for Google Cloud and CI with secret scanning.

Still to come in M0: passkey sign-in, resume import (JSON Resume and PDF), and
starting US carrier registration for check-in texts.

## The 2014 to 2017 R-Card code

This repository used to hold R-Card. None of that code carries forward, and
`main` starts from a clean history. The old code stays on the deprecated
`master` and `develop` branches. Don't branch from them or merge them in:
their history contains credentials that must be treated as compromised.
