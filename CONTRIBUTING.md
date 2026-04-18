# Contributing

Welcome. This is a Django + React app with a few opinionated conventions;
the full story lives in [`CLAUDE.md`](./CLAUDE.md) — this file is a
short pointer to the day-one essentials.

## Setup

```bash
cp .env.example .env             # fill in PARENT_PASSWORD, CHILD_PASSWORD
docker compose up --build
docker compose exec django python manage.py migrate --noinput
docker compose exec django python manage.py seed_data --noinput
docker compose exec django python manage.py createsuperuser
```

Dev frontend (optional, runs outside Docker with a Vite proxy to `:8000`):

```bash
cd frontend
npm install
npm run dev                      # :3000, /api proxied to :8000
```

## Running tests

```bash
# Backend
docker compose exec django python manage.py test

# Frontend
cd frontend
npm run lint
npm run test:run                 # one-shot
npm run test:coverage            # gated in CI
```

CI runs both suites on every push to `main`; see
[`.github/workflows/ci-cd.yml`](./.github/workflows/ci-cd.yml).

## Code style

- **Python** — `ruff` via [`pyproject.toml`](./pyproject.toml) (line-length 120,
  pycodestyle + pyflakes + flake8-logging-format + `no print()`).
  Run `ruff check apps config` locally.
- **JavaScript / JSX** — ESLint via
  [`frontend/eslint.config.js`](./frontend/eslint.config.js).
  Run `npm run lint` from `frontend/`.
- **Design system** — see
  [`frontend/src/components/README.md`](./frontend/src/components/README.md)
  for the Button / Form primitive / type-scale / z-index conventions.
  New interactive elements that call `POST`/`PATCH`/`DELETE` need a
  colocated `*.test.jsx` using `spyHandler` from
  [`frontend/src/test/spy.js`](./frontend/src/test/spy.js) — see
  [`CLAUDE.md`](./CLAUDE.md#frontend-testing-frontend) for the pattern.

## Pre-commit hooks (recommended)

Hooks live in [`.pre-commit-config.yaml`](./.pre-commit-config.yaml) and
catch the common slips (trailing whitespace, large files, ruff violations,
ESLint errors) before they hit CI:

```bash
pip install pre-commit
pre-commit install
# run on the whole repo on demand:
pre-commit run --all-files
```

## Commit & PR conventions

- Branch off `main`; keep PRs focused. Large refactors should land behind
  a short description of the migration path in the PR body.
- Update [`CLAUDE.md`](./CLAUDE.md) when you change anything a future
  contributor would benefit from knowing about — architecture, gotchas,
  env vars, new conventions.
- The deploy pipeline is blocking on backend tests, frontend tests
  (coverage gate 65/55/55/65), and the Trivy container scan. Don't merge
  red builds.

## Where to look for…

- **How an app fits together** → `CLAUDE.md` has a per-app breakdown
  under *Architecture*.
- **Why a decision was made** → read the owning service's module
  docstring first, then `docs/superpowers/specs/*` for the bigger designs.
- **How to back up / restore** → [`docs/operations/backup.md`](./docs/operations/backup.md).
- **Design-system primitives** → `frontend/src/components/README.md`.
- **RPG content** → `content/rpg/README.md` (YAML-first authoring).
