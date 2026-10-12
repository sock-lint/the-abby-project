# Pull request validation

Updated October 12, 2026 for the React Three Fiber/Capacitor application.
The owner authorized immediate Unity retirement because the app has no active
users. The [historical Unity runner instructions](unity-pr-validation.md) remain
available for source recovery, without active build or release requirements.

`.github/workflows/pr-validation.yml` runs for every PR to `main`, merge queue
request and manual dispatch. No path filters leave required checks pending.
Forks run on hosted infrastructure without production credentials.

| Required check | Validation | Runner |
| --- | --- | --- |
| `Frontend validation` | Lint, full coverage gate, web build and native staging build | GitHub-hosted Ubuntu, Node 22 |
| `API fixtures` | Real Django responses against synthetic fixtures and React consumption | GitHub-hosted Ubuntu, Python 3.12, Node 22 |

Keep strict `main` protection and these two required checks. Replace the retired
`Browser bridge` and `Unity validation` requirements; preserve unrelated
protection and merged-branch deletion settings. Workflow changes alone do not
edit repository protection.

From `frontend/`, reproduce with `npm ci`, `npm run lint`,
`npm run test:coverage -- --maxWorkers=4` and `npm run build`. Set shell variables
`ABBY_NATIVE_ENVIRONMENT=staging` and `ABBY_NATIVE_API_ORIGIN` to an isolated HTTPS
staging origin, then run `npm run build:native`. The CI origin
`https://staging.example.invalid` validates configuration without contacting a
backend; it is never an installable integration environment. Native sync and
physical-device limitations are documented in `frontend/CLAUDE.md`.

For contracts, set `SECRET_KEY` to a synthetic test-only value and
`DATABASE_URL=sqlite:///:memory:`, then run:

```powershell
python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures config.tests.test_greenlight_api_contract_fixtures config.tests.test_avatar_api_contract_fixtures
```

Fixtures do not replace permission, family-scoping or transaction tests. Add
affected endpoint tests, React interactions and PostgreSQL concurrency checks
when behavior changes. Retired Unity consumers remain reference source.

Private art does not enter hosted CI. Public builds exercise DOM/2D fallback;
local/private builds also validate converted models. Physical phones, signed
updates and lifecycle/media integration need acceptance outside these checks.
A native bundle build does not establish full workflow parity.
