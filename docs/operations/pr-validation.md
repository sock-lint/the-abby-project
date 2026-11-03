# Pull request validation

Updated October 21, 2026 for the React Three Fiber/Capacitor application.
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

The backend job has a **60-minute limit**, including service/dependency setup,
migrations, the full suite and cleanup. On October 27, 2026, the
[6,231-test run on `85c03c66`](https://github.com/sock-lint/the-abby-project/actions/runs/40531135277/job/122283927473)
reported all tests `OK` in 43 minutes 40 seconds, then exceeded the 45-minute
job limit during test-database cleanup. Its required check remained canceled;
the successful test summary alone does not satisfy the gate. The 60-minute cap
provides bounded setup, cleanup and hosted timing headroom while preserving
the single full PostgreSQL/Redis run and every assertion. The required check
still needs a complete successful result on the reviewed commit.

The former 30-minute limit canceled the
[5,200-test run on `3845ab36`](https://github.com/sock-lint/the-abby-project/actions/runs/39535329812/job/119010547059)
after 5,184 recorded passes and no recorded failures; 16 tests had no result, so
that run remained incomplete. It was still passing real migration tests near
cancellation. The earlier 5,077-test suite completed in 24 minutes 31 seconds;
comparison at the same late migration checkpoint projects roughly 32 minutes
including setup for the larger run, before the next merged test additions.
The subsequent 45-minute cap covered that projected growth until the larger
October 27 run exhausted it. A canceled run does not satisfy the gate.

From `frontend/`, reproduce with `npm ci`, `npm run lint`,
`npm run test:coverage -- --maxWorkers=4` and `npm run build`. Set shell variables
`ABBY_NATIVE_ENVIRONMENT=staging` and `ABBY_NATIVE_API_ORIGIN` to an isolated HTTPS
staging origin, then run `npm run build:native`. The CI origin
`https://staging.example.invalid` validates configuration without contacting a
backend; it is never an installable integration environment. Native sync and
physical-device limitations are documented in `frontend/CLAUDE.md`.

The egg discovery preview additionally runs
`config.tests.test_egg_discovery_api_contract_fixtures` in the hosted fixture
comparison and `src/api/eggDiscoveryContractFixtures.test.jsx` in its React
consumer step. Source integration is covered by
`config.tests.test_egg_discovery_source_adapters`; the full backend job also
executes `apps.egg_discoveries`, including its PostgreSQL concurrency tests.

For contracts, set `SECRET_KEY` to a synthetic test-only value and
`DATABASE_URL=sqlite:///:memory:`, then run:

```powershell
python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures config.tests.test_greenlight_api_contract_fixtures config.tests.test_avatar_api_contract_fixtures config.tests.test_rpg_integrity_api_contract_fixtures config.tests.test_catalog_api_contract_fixtures config.tests.test_catalog_icon_api_contract_fixtures config.tests.test_report_card_api_contract_fixtures config.tests.test_challenge_api_contract_fixtures config.tests.test_homework_ai_api_contract_fixtures config.tests.test_project_ai_api_contract_fixtures config.tests.test_material_api_contract_fixtures config.tests.test_reading_api_contract_fixtures config.tests.test_template_api_contract_fixtures config.tests.test_lifecycle_api_contract_fixtures config.tests.test_google_auth_api_contract_fixtures config.tests.test_submission_timing_api_contract_fixtures config.tests.test_drive_export_api_contract_fixtures config.tests.test_elemental_art_api_contract_fixtures config.tests.test_hatchery_discovery_api_contract_fixtures config.tests.test_parent_api_contract_fixtures config.tests.test_printing_api_contract_fixtures config.tests.test_taxonomy_delete_api_contract_fixtures
python manage.py test --settings=config.settings_test config.tests.test_progression_api_contract_fixtures config.tests.test_content_workbench_api_contract_fixtures config.tests.test_taxonomy_retirement_api_contract_fixtures config.tests.test_journal_api_contract_fixtures config.tests.test_lorebook_api_contract_fixtures config.tests.test_oauth_api_contract_fixtures
```

From `frontend/`, run the matching consumers:

```powershell
npm run test:run -- src/api/sharedContractFixtures.test.js src/api/avatarContractFixtures.test.js src/api/rpgIntegrityContractFixtures.test.jsx src/api/catalogContractFixtures.test.js src/api/reportCardContractFixtures.test.js src/api/challengeContractFixtures.test.js src/api/voyagerFeedbackContractFixtures.test.js src/api/homeworkAIContractFixtures.test.js src/api/projectAIContractFixtures.test.js src/api/materialContractFixtures.test.js src/api/readingContractFixtures.test.js src/api/templateContractFixtures.test.js src/api/accountLifecycleContractFixtures.test.js src/api/googleAuthContracts.test.js src/api/submissionTimingContractFixtures.test.jsx src/api/googleDriveContracts.test.js src/api/parentContractFixtures.test.jsx src/api/printingContractFixtures.test.js src/api/taxonomyContractFixtures.test.jsx
npm run test:run -- src/api/progressionLabContractFixtures.test.js src/api/contentWorkbenchContractFixtures.test.jsx src/api/taxonomyRetirementContractFixtures.test.jsx src/api/journalContractFixtures.test.js src/api/lorebookContractFixtures.test.jsx src/pages/Manage.oauth.test.jsx
```

Archive and participant-privacy contracts additionally run
`config.tests.test_authoring_archive_api_contract_fixtures` and
`config.tests.test_participant_privacy_api_contract_fixtures`, with
`src/api/authoringArchiveContractFixtures.test.js` and the existing challenge
fixture consumer. These verify real archive/history/restore receipts, retry
state, and retained legacy contributions without departed profile names.

The catalog producer/consumer pair uses production asset support and checks
available offers separately from retained saved ownership. Historical breeding fixtures are retained only for retired Unity reference; active contracts verify HTTP 410 and inert compatibility fields. For
catalog changes, also run:

```powershell
python manage.py test --settings=config.settings_test apps.rpg.tests.test_catalog_support apps.rpg.tests.test_asset_supported_acquisition apps.rpg.tests.test_catalog_consumers apps.pets.tests.test_asset_supported_catalog
```

Run `apps.pets.tests.test_incubation` for start, wait, claim, replay and retired
instant-hatch behavior. Run `apps.pets.tests.test_catalog_concurrency` with
`config.settings_test` and a disposable PostgreSQL database for competing
incubation starts, ready hatch claims and final-feed transactions;
SQLite skips these row-lock checks. React Saved collection coverage lives in
`src/pages/bestiary/party/SavedPetCollections.test.jsx` and the affected Profile,
Inventory, Hatching and reward/challenge tests within the full coverage gate.

The journal producer/consumer pair verifies new saves, exact UUID replays, today
reads and edits against the same measured XP/Coin receipt. Summary fixtures keep
legacy daily notes in the same history with unavailable historical receipts;
parent responses exclude private notes and journals. Old-client note saves and
new journal saves share one daily Coin acknowledgment.
Journal and challenge fixtures also exercise MCP taxonomy renames followed by
real REST activity saves: journal retains the original 10/5 XP split and the
untagged daily bonus retains 20 Persistence XP. Registered-SDK regressions in
`apps.mcp_server.tests.test_fixed_reward_source_identity` cover source reloads,
reparenting, retirement, ambiguity, unlock eligibility and receipt replay.
The report-card and parent contract pairs additionally verify renamed grade XP
and inactive-child physical handover. MCP regressions cover current habit/daily
authority and saved experiment decisions. Run their PostgreSQL concurrency tests
with main settings: `test_habit_daily_authority_concurrency`,
`test_decision_catalog_freshness`, `test_experiment_lock_scope` and
`test_experiment_retry_concurrency` under `apps.mcp_server.tests`. The decision
checks cover a cross-family catalog edit between preparation and commit, source
read/write fences, and continued unrelated-family activity during computation.

Run `apps.achievements.tests.test_mastery_source_identity` for named badge
criteria across taxonomy edits, and `test_reading_forecast_identity` and
`test_deleted_pack_publication_replay` under `apps.mcp_server.tests` for native
Reading forecast parity and completed publication retries after source disposal.
These use synthetic registered MCP calls with native award/receipt controls.

Lab taxonomy coverage is `apps.mcp_server.tests.test_lab_source_identity`,
`apps.mcp_server.tests.test_lab_identity_freshness` and
`apps.rpg.tests.test_progression_taxonomy_snapshot`. The freshness concurrency
checks require disposable PostgreSQL: metadata edits must block during capture
and final save, fail a decision after capture, and leave household XP activity
unblocked during detached catalog work. The real Lab producer/React pair also
checks a renamed-taxonomy Reading/mastery report.

`apps.mcp_server.tests.test_lab_fixed_xp_routes` compares journal allocation and
untagged daily-bonus fallback forecasts with native receipts and per-skill XP.
It covers retained names, retirement/reparenting, ambiguity, partial resolution,
locked destinations, nonempty activity-tag priority and finite badge capacity.
Short-session controls use the actual rounded project XP and combined daily
qualifying minutes when checking finite badge capacity.
The real Lab producer/React pair also consumes the renamed fixed-route report,
with 450 journal XP and 600 daily-bonus XP over thirty active days. Forecast
purity checks prohibit household reads and native reward writers.

`apps.rpg.tests.test_content_runtime_levels` and
`apps.mcp_server.tests.test_content_runtime_levels` check runtime-derived badge
and prerequisite bounds, atomic preview/publication rejection, native level-6
controls and legacy level-0 YAML prerequisite compatibility. They also retain
earned unavailable-level badges and payouts while hiding unreachable new goals.
The real `badges-retained-unreachable-level.json` producer/React pair checks the
same retained catalog response; reads cannot rewrite rewards or history.
`test_category_projects_compatibility` and `test_legacy_runtime_level_visibility`
under `apps.achievements.tests` retain current case-variant category unions,
uncategorized-project rules and native-compatible saved level thresholds,
including count-based goals that qualify with zero matching rows.
`apps.rpg.tests.test_progression_legacy_runtime_levels` compares those thresholds
with native eligibility, including integer-query rounding and missing progress.
The catalog producer/React pair also consumes `badges-reachable-legacy-levels.json`.
`apps.achievements.tests.test_named_goal_ambiguity` checks that retained/current
category ties stop being offered as goals while earned history remains visible;
current-name unions and uncategorized, plural and zero-count rules remain valid.
The real producer/React pair consumes `badges-retained-category-tie.json`.
`apps.mcp_server.tests.test_category_rename_admission` covers atomic rejection
through MCP, REST and reviewed pack preview/publication, preserving current-name
unions, case-only renames, first-source identity and legacy repair rules.

`apps.rpg.tests.test_loader_category_source_conflicts` checks manual rollback
and selective startup deferral. `test_startup_quest_badge_closure` under that
same package covers forward cross-pack dependencies, saved prerequisite
overrides, safe alternative goals and retained history. They also check saved
completion capacity across source orders, retraction of transient plans and
bounded conditional cycles without withholding reachable downstream goals.
They distinguish badges written earlier in the same batch from saved badges
whose source edits were withheld, and keep actual loading refusals across later
planning passes. Dependency-component cases bound repeated badge checks, with
disconnected valid edits and independent source conflicts as controls. Coupled
capacity cases require a retained-rule plan to remain supported without forcing
that choice; actual source conflicts remain strict.
`test_stale_category_source_identity` checks category recovery when only
orphaned provenance remains, while live identities and keyed claims stay
protected. MCP's `test_category_retained_repair_admission` checks departures
that would otherwise strand the supported rename-back repair.
`apps.achievements.tests.test_named_goal_availability_queries`, MCP's
`test_named_goal_catalog_queries` and RPG's
`test_progression_named_goal_queries` bound selector queries in REST reads,
MCP pages and detached Lab snapshots, including pagination, source limits,
fresh reads and the 512-badge Lab limit.

Progression Lab's incubation projection is covered by
`apps.rpg.tests.test_progression_incubation`, its real API fixture producer,
and the React Lab tests. Check consumed ingredients without early ownership,
one unfinished slot, inactive-day readiness, next-active-visit claims, recorded
policy/fingerprint changes and missing historical policy. These tests remain
in memory or use disposable synthetic data; they never exercise household care.

Exchange decisions additionally run
`apps.mcp_server.tests.test_exchange_family_boundaries` and
`test_exchange_family_boundaries_concurrency` with disposable PostgreSQL.
They check foreign and missing request refusals, current actor and member
admission, native decision parity, notes, once-only settlement, owner changes
and native-versus-MCP lock contention. Both workers close their physical
connections before test-database teardown. With PostgreSQL,
`apps.rewards.tests.test_exchange_deleted_owner` races real child deletion with
REST approval/rejection: a vanished owner returns 404 without settlement writes.
Native reward decision and wallet concurrency checks remain required.

`apps.rpg.tests.test_workbench_named_goal_queries` bounds the native REST
content editor's named badge and quest-prerequisite lookups, preserving
availability, editability, shop uses, catalog limits and fresh reads.
The bundled-content command tests retain complete batch planning, ordered
loading, explicit-pack behavior and rollback after an actual later failure.
`apps.rpg.tests.test_startup_preflight_planning_context` requires planning errors
to identify the supplying pack at the first, middle and last selected positions,
including entries scanned by another loader, in normal and dry-run loads.
`test_startup_legacy_badge_planning` keeps non-strict legacy badge criteria
loadable during selective planning without changing saved criteria. It retains
missing-content deferrals for valid counted goals and checks dry-run rollback,
repeated loads, native numeric-count coercion and surviving any-of alternatives.
Bundled preflight tests retain parser details, grouped successful headers,
manual strictness and dry-run rollback. `test_startup_live_deferral_warnings`
under the same package retains the original named cause across real cross-pack
deferrals without repeatedly prefixing it.

OAuth client management shares `contracts/api/fixtures/oauth-applications.json` between
`config.tests.test_oauth_api_contract_fixtures` and `src/pages/Manage.oauth.test.jsx`.
The producer authenticates a staff parent and keeps another family's active token
private while preventing that registration's removal. The management-page checks
cover removal confirmation, cancellation, refreshed rows and a stale-eligibility
conflict. Run `config.tests.test_oauth_client_cleanup` for deletion permissions,
access/refresh/code blockers, and `config.tests.test_oauth_cleanup_concurrency`
for issuance races on disposable PostgreSQL.

Fixtures do not replace permission, family-scoping or transaction tests. Add
affected endpoint tests, React interactions and PostgreSQL concurrency checks
when behavior changes. Retired Unity consumers remain reference source.

The Usage report adds `config.tests.test_usage_api_contract_fixtures` and
`src/api/usageContractFixtures.test.js` to the required fixture job. Focused
behavioral checks are `apps.usage` and the frontend Usage dashboard/visit tests;
`npm run test:pwa -- e2e/usage-dashboard.pw.js` exercises the actual app route,
scope selection, denied access, keyboard refresh and 320/390/1280px layouts with
synthetic responses. These tests never contact production.

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
