# Working on Plytos

Plytos is a mobile-first web app where job seekers keep evidence-backed
"strength cards" with full version history. Read `README.md` for layout and
`docs/data-model.md` before touching cards, versions or the schema.

## Commands

- API (`services/api`): `uv sync --all-extras`, `uv run ruff check .`,
  `uv run ruff format .`, `uv run mypy`, `uv run pytest`. Tests need Postgres:
  `docker compose up -d db` from the repo root, or set `PLYTOS_TEST_ADMIN_URL`.
- Web (`apps/web`): `npm ci`, `npm run lint`, `npm run typecheck`, `npm test`,
  `npm run build`.
- Terraform (`infra/terraform`): `terraform fmt -recursive`,
  `terraform init -backend=false && terraform validate`.

Run the checks for whatever you changed before pushing. CI runs all of them
plus a gitleaks secret scan.

## Rules that must not break

- **No secrets in the repo.** Credentials go in Secret Manager or come from
  service identity. Never commit `.env` files, keys or service account JSON.
- **Never branch from or merge `master` or `develop`.** They hold the old
  R-Card code and leaked credentials.
- **Schema changes are new migration files.** Never edit an applied migration;
  the runner refuses changed checksums.
- **Every person-owned table gets `owner_id`, row-level security, and a test
  that another person can't read it.** The app connects as `plytos_app`, which
  never owns tables.
- **Card versions and events are append-only.** Don't grant update or delete
  on them; corrections are new versions.
- **Variants carry framing only.** Facts change only on the main line.
- **Card content is encrypted with the owner's data key.** Don't store card
  text, target names or notes in clear columns, logs or events.
- **No public pages or public API in v1.** Keep `noindex` headers, the
  robots disallow, and IAM-only access to the API.
- **AI proposes, the person decides.** AI output becomes a version only when
  the person accepts it, and is recorded with `author_kind = 'ai'`.
- **Good on every screen, iOS first.** Design for phone, tablet and laptop
  alike, leaning on iOS conventions; the app will be iOS first.
- **No real resumes in the repo.** Import tests use made-up people built in
  code (`services/api/tests/resume_samples.py`). Don't commit resume files,
  their text, or audit output from a real person's resume. Resume text never
  goes in logs, URLs or error messages.
