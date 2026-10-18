# Pull request validation

Updated October 13, 2026 for the React Three Fiber/Capacitor application.
The owner authorized immediate Unity retirement because the app has no active
users. The [historical Unity runner instructions](unity-pr-validation.md) remain
available for source recovery, without active build or release requirements.

`.github/workflows/pr-validation.yml` runs for every PR to `main`, merge queue
request and manual dispatch. No path filters leave required checks pending.
Forks run on hosted infrastructure without production credentials.

| Required check | Validation | Runner |
| --- | --- | --- |
| `Frontend validation` | Lint, full coverage gate, web build and native staging build | GitHub-hosted Ubuntu, Node 22 |
| `Backend validation` | Migrations and the full Django suite, including PostgreSQL transaction/locking checks | GitHub-hosted Ubuntu, Python 3.12, PostgreSQL 16, Redis 7 |
| `API fixtures` | Real Django responses against synthetic fixtures and React consumption | GitHub-hosted Ubuntu, Python 3.12, Node 22 |

Keep strict `main` protection and these three required checks. Add
`Backend validation` to the existing required checks after its first successful
PR run, before enabling the [autonomous improvement loop](improvement-loop.md).
Replace the retired
`Browser bridge` and `Unity validation` requirements; preserve unrelated
protection and merged-branch deletion settings. Workflow changes alone do not
edit repository protection.

The backend gate uses the same disposable PostgreSQL 16 and Redis 7 services
as post-merge CI/CD, with synthetic credentials and no production secrets.
PostgreSQL data lives on a bounded 1 GiB tmpfs. Migrations and the complete
suite run with the main settings so database constraints, row locks and real
Redis integration are checked before merge. Reproduce with isolated test
services, `SECRET_KEY`, `DATABASE_URL`, `REDIS_URL` and `CELERY_BROKER_URL`, then
run `python manage.py migrate --noinput` and
`python manage.py test --noinput --verbosity=2`. Never point these commands at
the production database. SQLite fixture checks remain useful contract checks;
they do not satisfy this backend gate.

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
python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures config.tests.test_greenlight_api_contract_fixtures config.tests.test_avatar_api_contract_fixtures config.tests.test_rpg_integrity_api_contract_fixtures config.tests.test_catalog_api_contract_fixtures config.tests.test_catalog_icon_api_contract_fixtures config.tests.test_report_card_api_contract_fixtures config.tests.test_challenge_api_contract_fixtures config.tests.test_homework_ai_api_contract_fixtures config.tests.test_project_ai_api_contract_fixtures config.tests.test_material_api_contract_fixtures config.tests.test_reading_api_contract_fixtures config.tests.test_template_api_contract_fixtures config.tests.test_lifecycle_api_contract_fixtures config.tests.test_google_auth_api_contract_fixtures config.tests.test_submission_timing_api_contract_fixtures
```

From `frontend/`, run the matching consumers:

```powershell
npm run test:run -- src/api/sharedContractFixtures.test.js src/api/avatarContractFixtures.test.js src/api/rpgIntegrityContractFixtures.test.jsx src/api/catalogContractFixtures.test.js src/api/reportCardContractFixtures.test.js src/api/challengeContractFixtures.test.js src/api/homeworkAIContractFixtures.test.js src/api/projectAIContractFixtures.test.js src/api/materialContractFixtures.test.js src/api/readingContractFixtures.test.js src/api/templateContractFixtures.test.js src/api/accountLifecycleContractFixtures.test.js src/api/googleAuthContracts.test.js src/api/submissionTimingContractFixtures.test.jsx
```

The catalog producer/consumer pair uses production asset support and checks
available offers separately from retained saved ownership. Broader breeding
fixtures use an explicit scoped synthetic policy for engine mechanics. For
catalog changes, also run:

```powershell
python manage.py test --settings=config.settings_test apps.rpg.tests.test_catalog_support apps.rpg.tests.test_asset_supported_acquisition apps.rpg.tests.test_catalog_consumers apps.pets.tests.test_asset_supported_catalog
```

Run `apps.pets.tests.test_catalog_concurrency` with `config.settings_test` and a
disposable PostgreSQL database for competing hatch/final-feed transactions;
SQLite skips these row-lock checks. React Saved collection coverage lives in
`src/pages/bestiary/party/SavedPetCollections.test.jsx` and the affected Profile,
Inventory, Hatching and reward/challenge tests within the full coverage gate.

Fixtures do not replace permission, family-scoping or transaction tests. Add
affected endpoint tests, React interactions and PostgreSQL concurrency checks
when behavior changes. Retired Unity consumers remain reference source.

Private art does not enter hosted CI. Public builds exercise DOM/2D fallback;
local/private builds also validate converted models. Physical phones, signed
updates and lifecycle/media integration need acceptance outside these checks.
A native bundle build does not establish full workflow parity.

Backend validation also runs `python -m unittest discover -s scripts/r3f
-p 'test_prepare_*.py' -v` against synthetic source/evidence fixtures. These
check explicit source maps, preserved originals, private temporary output,
review requirements and bounded conversion reports without Blender or paid art.
The separate `test_blender_archer.py` math checks require local Blender/bpy;
hosted guards do not claim that they or real Archer renders were executed.

The backend gate also evaluates both staging Compose recipes with synthetic
configuration through `scripts/operations/test_staging_recipe.py`. It checks
database/runtime isolation, unpublished container ports and staging-only
transport-peer/forwarded-HTTPS labels, explicit build secrets and external
database volume preservation. It does not contact staging or establish
Cloudflare Access, live proxy routing or native-device acceptance.
