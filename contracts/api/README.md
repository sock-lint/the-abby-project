# Shared API response fixtures

`progression-lab-metadata.json`, `progression-lab-report.json` and
`progression-lab-economy-report.json` bind anonymous new-child forecasts to
their real staff-parent endpoints. The economy example uses synthetic reward
offers and print estimates, a calendar-month budget and assumed approved money
earnings. Coin spending, money exchanged and estimated fulfillment costs remain
separate; these fixtures contain no real shop, family financial data or cash-out
value. Producers live in `config/tests/test_progression_api_contract_fixtures.py`;
React transport and report checks live in
`frontend/src/api/progressionLabContractFixtures.test.js` and the Progression Lab
page tests.

`progression-lab-reward-budget-report.json` adds a synthetic shared daily
expedition/pouch Coin allowance to the same endpoint. Its normalized scenario
and report distinguish requested, credited and omitted automatic Coins,
including expedition salvage, without altering parent-authored chore rewards
or any live economy rule. Metadata publishes the nullable whole-Coin bound;
legacy routines omit the field and retain uncapped behavior.

`completion-timing-weekly-pending.json`, `completion-timing-chore-reviewed.json`,
`completion-timing-homework-reviewed.json` and
`completion-timing-homework-assignment.json` come from the real submission/read
endpoints. They distinguish the weekly Monday period from a Friday submission,
the original homework deadline from a later edit, and a later parent approval.
`timing_snapshot` v1 freezes `timezone`, `submitted_at`, `submitted_on`,
`schedule`, `period_start`, `period_end`, `due_on` and `timeliness`. Legacy rows
remain null. Read-only nullable `current_due_date` is today's editable deadline,
not historical evidence. Parent reviewed history uses the normal paginated
`?status=reviewed&user_id=<verified child>` filters. Challenge payloads add
nullable `completed_at`; legacy quest history does not invent a timestamp.
The producer is `config.tests.test_submission_timing_api_contract_fixtures` and
the React consumer is `src/api/submissionTimingContractFixtures.test.jsx`;
both run in the required API fixtures workflow.

`content-workbench-catalog.json` and `content-workbench-denied.json` bind the
staff content editor's catalog, exact reward references, reverse item uses,
simulation metadata and permission denial to real Django responses. Producers
live in `config/tests/test_content_workbench_api_contract_fixtures.py`; React
transport and editor consumption checks live in
`frontend/src/api/contentWorkbenchContractFixtures.test.jsx`.

`badges-rarity-bonuses.json` and `badges-earned-rarity-bonuses.json` verify real catalog/earned responses, opt-outs and family isolation.

Rarity responses include server-derived badge `coin_bonus` (base, before a
Lucky Coin boost), item `effect_summary` and authenticated `acquisition_sources`
(`kind`, `name`, internal `path`). Companion species expose acquisition `rarity`;
owned pets/mounts expose the higher species/saved-potion tier. New goal promises
and receipts include item rarity, artwork, type and effect details; historical
sparse receipts remain valid and are not rewritten. Recent drops include item
details and nullable `salvage_coins`: null means the older exact payout was not
recorded, rather than zero. Availability reflects today's action eligibility
independently of preserved ownership and accepted item promises.

`fixtures/*.json` contains raw Django response bodies shared by the React tests
and retained Unity reference checks. Unity is retired and is not an active release
gate. Keep the files here rather than copying sample
payloads into each client. No production credentials or user data belong here.
The login token and all identities are synthetic and exist only in the test DB.

| Fixture | Endpoint / scenario |
| --- | --- |
| `api-not-found.json` | Unknown `/api/` paths return JSON 404s instead of the SPA's HTML/200; routing and React client checks preserve the generic error without retries or echoed request values |
| `lifecycle-preview.json`, `lifecycle-child-preview.json`, `lifecycle-close-preview.json` | Self-scoped Settings impact review, active parent successors, shared ownership counts and a membership fingerprint; child privacy and sole-active-parent closure remain distinct |
| `template-skills.json` | Parent `GET /api/templates/1/`; reusable plans preserve weighted project skill tags and fixed milestone XP tags |
| `catalog-icons-items.json`, `catalog-icons-challenges.json`, `catalog-icons-species.json` | Parent catalog responses expose server-verified image asset IDs; shared sprite keys and equally named custom challenges stay distinct |
| `catalog-icons-drops.json`, `catalog-icons-goals.json` | Recent drops, automatic goals and reward previews retain verified image IDs while same-name parent goals keep null |
| `artwork-categories.json`, `artwork-subjects.json`, `artwork-skills.json`, `artwork-tree.json`, `artwork-progress.json` | Skill catalog, nested tree and saved progress expose exact artwork identities with category/subject context; equally named custom skills retain null |
| `artwork-badges.json`, `artwork-summary.json`, `artwork-character.json`, `artwork-dashboard.json` | Exact final badge criteria select artwork across catalog, earned summary, trophy and dashboard; changed criteria retain null |
| `clock-idle.json`, `clock-active.json` | Authenticated `GET /api/clock/`; JSON `null` when idle and the self-scoped serialized entry while running, both HTTP 200 with `application/json` |
| `printing-budget-configured.json` | Parent enables a per-child print exchange rate of one minute per coin |
| `printing-request-quoted.json`, `printing-requests-quoted.json` | Parent reviews 61 estimated minutes; the child sees the frozen 61-coin quote in the detail and list responses |
| `printing-project-request.json`, `printing-project-requests.json` | Authenticated detail and project-filtered list retain the optional project identity/title without widening print ownership |
| `printing-project-unavailable.json`, `printing-project-requests-unavailable.json` | An existing print remains readable after cross-family project reassignment, with project identity/title hidden in both detail and list |
| `printing-exchange-paid.json` | Child accepts the saved quote once; request becomes approved with 61 coins paid |
| `printing-cancel-refunded.json` | Cancellation before the first job returns the exact charge once |
| `printing-exchange-invalid.json`, `printing-request-not-owned.json` | Caller-supplied prices/accounts and another family's request are rejected without spending |
| `challenge-goal-created.json` | `POST /api/challenges/goals/`; parent-created repeating weekly running goal with decimal distance and an unpaid reward preview |
| `challenges-initial.json` | `GET /api/challenges/`; personal parent goal and eligible catalog goal track automatically before either is pinned |
| `challenges-origins.json` | Same list endpoint; parent, retired catalog and saved legacy goals retain distinct server-owned origins despite identical names |
| `challenge-pinned.json`, `challenge-unpinned.json` | `POST`/`DELETE /api/challenges/goal:1/pin/`; self-scoped presentation preference, without progress or rewards |
| `challenge-run-first.json` | `POST /api/movement-sessions/`; real 0.75-mile run advances multiple goals and qualifies the daily bonus |
| `challenges-partial.json` | Goal list retains progress on both the pinned distance goal and unpinned count goal, with the automatic daily reward receipt |
| `challenge-run-completed.json` | Second real run adds 1.25 miles and completes matching goals while no goal is pinned |
| `challenges-completed.json` | Completed occurrences retain reward previews and actual paid receipts; reopening the list awards nothing |
| `challenges-boosted.json` | Daily Lucky Coin payout is distinct from its base preview; parent goal Coins retain the existing unboosted policy |
| `challenges-items-delivered.json` | Actual frame delivery is recorded in the awarded receipt and persists without duplicate grants |
| `challenges-items-skipped.json` | An egg unavailable before acceptance is excluded from the new snapshot and receives no item delivery |
| `challenges-items-promised-retired.json` | An accepted frozen item remains visible and delivers once after catalog retirement |
| `challenges-legacy-promised-item.json`, `quest-promised-item-active.json`, `quest-promised-item-history.json` | Accepted legacy quest items remain visible and fulfill once after retirement; new starts omit unavailable items |
| `challenges-items-converted.json` | An egg for an already-owned mount is converted to Coins; the receipt distinguishes conversion from delivery |
| `challenge-goal-invalid.json` | Invalid nonpositive target rejected with HTTP 400; no goal or reward persists |
| `character-avatar-default.json` | `GET /api/character/`; existing account with no saved Archer appearance receives the complete default options |
| `character-avatar-saved.json` | `POST /api/character/avatar/`; confirmed self-scoped appearance save returns the full character, also returned on later reads and retries |
| `character-avatar-legacy.json` | `GET /api/character/`; a legacy four-option saved look retains its choices and projects the default costume, face, ears and empty wardrobe without writing |
| `character-avatar-invalid.json` | Avatar save rejected with HTTP 400 for an unsupported outfit, without writes |
| `avatar-catalog.json` | Authenticated `GET /api/character/avatar/catalog/`; ordered base controls, shared item IDs and explicitly supported attachment bindings |
| `character-avatar-configuration-saved.json` | Generic configuration save/retry and read, with shared equipment and a synchronized legacy Archer projection |
| `character-avatar-configuration-invalid.json` | Generic equipment rejected with HTTP 400 for an unfit slot, without writes |
| `report-card-created.json` | `POST /api/chronicle/grades/`; private quarterly report card with percentage, points and letter subjects and a verified recognition receipt |
| `report-cards-list.json` | `GET /api/chronicle/grades/`; quarter and semester report cards in the existing paginated grade history |
| `report-card-corrected.json` | `PATCH /api/chronicle/301/grade/`; corrected and shared report card keeps its original save identity and reward receipt |
| `report-card-invalid.json` | Report card rejected with HTTP 400 for an unknown subject field; indexed nested errors and no saved result or reward |
| `pet-feed-fledgling.json`, `pet-feed-bird.json` | Real feed receipts cross 50-growth Fledgling and confirmed 100-growth Bird thresholds |
| `pets-stable-fledgling.json`, `pets-stable-bird.json` | Stable reload preserves exact Base Chick stage; Bird includes the confirmed mount |
| `pets-supported-catalog.json` | `GET /api/pets/codex/`; production policy advertises 15 exact Base-only families |
| `pets-preserved-collection.json` | `GET /api/pets/stable/`; supported Chick and earlier Cat ownership coexist, with catalog availability flags and preserved growth |
| `cosmetics-supported-catalog.json` | `GET /api/cosmetics/catalog/`; available Frames/Titles/Covers slots, retained empty accessory slot |
| `inventory-appearance.json` | `GET /api/inventory/`; owned frame links to Profile while owned color theme links to Settings → Appearance |
| `items-preserved-inventory.json` | `GET /api/inventory/`; unavailable saved egg/accessory entries remain owned without blocked actions |
| `pet-hatch-unavailable.json` | Unsupported saved egg rejected with HTTP 400 without consuming either ingredient |
| `cosmetic-equip-unavailable.json` | Owned saved accessory equip rejected with HTTP 400 without changing ownership or selection |
| `google-drive-config.json` | `GET /api/auth/google/drive/config/`; public Picker configuration with synthetic keys |
| `google-drive-file.json` | `POST /api/auth/google/drive/file/`; verified metadata for a parent-selected school PDF, without credentials |
| `google-drive-sources-page-1.json`, `google-drive-sources-page-2.json` | Parent-only stored project-photo source list, scoped and paginated without media/storage URLs |
| `google-drive-sources-empty.json` | Parent's empty imported-PDF source list |
| `google-drive-uploaded-file.json` | Confirmed copy of an authorized Abby photo in My Drive, using the existing resource metadata shape |
| `google-auth-busy.json` | Google authorization start rejected with HTTP 503 at retained-transaction capacity, without saving another verifier or changing the user's credential |
| `homework-ai-default.json` | Parent `GET`/`PUT`/`DELETE /api/homework/ai-settings/`; disconnected family Planning AI connection |
| `homework-ai-openai.json`, `homework-ai-anthropic.json` | Parent-saved family provider and model; only saved-key presence is returned |
| `project-ai-plan-new.json` | Parent `POST /api/projects/plan/`; reviewable milestones, steps and materials without creating a project |
| `project-ai-plan-existing.json` | Parent `POST /api/projects/401/plan/`; reviewable additions with the existing project's opaque plan version |
| `project-ai-plan-applied.json` | Parent `POST /api/projects/401/apply-plan/`; confirmed atomic append of the reviewed plan |
| `project-work-detail.json` | Child `GET /api/projects/401/`; ordinary project explicitly reports `is_homework_plan: false` and a null homework assignment link |
| `homework-plan-detail.json`, `homework-with-plan.json` | Parent and child read a legacy linked homework plan and its original assignment; planning steps remain available through the assignment |
| `projects-with-homework-plan.json` | Parent and child `GET /api/projects/`; linked homework planning rows are excluded from the project list |
| `homework-plan-clock-denied.json` | Child `POST /api/clock/` for a homework plan returns HTTP 400 without creating time or changing the plan status |
| `material-unready.json`, `material-list.json` | Material detail and paginated list retain an estimate without claiming readiness, a purchase or actual spending; clearing an on-hand mark returns the same unready detail |
| `material-ready.json` | `POST /api/projects/401/materials/701/mark-ready/`; owned or borrowed supplies become ready without recording a purchase |
| `material-purchased-zero.json`, `material-purchased.json` | Existing purchase action preserves explicit zero or positive actual cost and also reports readiness |
| `material-not-owned.json` | Another family's readiness write is rejected with HTTP 404 without changing the material |
| `parent-family-overview.json` | Parent dashboard with household-local homework, chores, goals, safe accomplishments and clocked estimates; no private journal/submission bodies |
| `parent-reward-approved.json`, `parent-reward-delivered.json` | Distinct real-world approval and handover receipts, preserving approval audit and recording explicit delivery without another reward/payment |
| `auth-login-child.json` | `POST /api/auth/`, successful password login; flat user plus token |
| `auth-me-child.json` | `GET /api/auth/me/`, authenticated child identity |
| `habits-page-1.json` | `GET /api/habits/`, first 20 of 21 child-visible rituals |
| `habits-page-2.json` | `GET /api/habits/?page=2`, final ritual and null `next` |
| `habits-empty.json` | `GET /api/habits/`, no published rituals |
| `notifications-page-1.json` | `GET /api/notifications/`, first 20 of 21 self-scoped unread updates; root-relative continuation with a synthetic GET namespace |
| `notifications-page-2.json` | Final unread update, null `next` and a root-relative `previous` link |
| `notifications-empty.json` | Same notification endpoint with no updates |
| `habit-positive-tap.json` | `POST /api/habits/9/log/`, persisted `direction: 1` tap and real game event |
| `habit-positive-tap-no-event.json` | Same tap with the optional game-loop result explicitly absent |
| `habit-positive-tap-limit.json` | Same-day repeat rejected with HTTP 400; no second tap persists |
| `habit-coop-completed.json` | A real habit tap completes a custom co-op quest; the ordinary game event retains the finishing child's full reward receipt |
| `quest-nonrepeatable-restart.json` | Restarting that completed nonrepeatable quest is rejected with HTTP 400 and no further grants |
| `greenlight-overview-no-snapshot.json` | `GET /api/payments/greenlight/overview/?user_id=7`; money owed, approved payable and pending hourly earnings, with unknown external balance |
| `greenlight-balance-snapshot.json` | `POST /api/payments/greenlight/snapshot/`; parent-reported Greenlight balance with its observation time |
| `greenlight-overview.json` | Overview with a separately reported Greenlight balance; recording the observation changes no earnings or debt |
| `greenlight-payout.json` | `POST /api/payments/greenlight/payout/`; confirmed manual transfer pays an approved timecard exactly once |
| `greenlight-preview.json` | `POST /api/payments/greenlight/preview/`; match candidate, new transfer and excluded card purchase, without writes |
| `greenlight-reconcile.json` | `POST /api/payments/greenlight/reconcile/`; one existing payout matched and one new payout recorded |
| `greenlight-overview-reconciled.json` | Final overview after reconciliation; debt decreases, pending hourly earnings and balance observation stay separate |
| `timecard-closed.json`, `timecard-closed-detail.json` | Parent `POST /api/timecards/13/close/` and later detail read; approved $0 week closes without a payout, retaining hours and approval audit |
| `pets-stable.json` | `GET /api/pets/stable/`, owned pets and mounts with nested species/potions, growth, happiness and active state |
| `pets-stable-empty.json` | Same stable endpoint with no owned companions; catalog total remains populated |
| `pets-stable-restricted-empty.json` | Empty stable with a restricted species; `total_possible` counts only supported potion combinations |
| `inventory-food.json` | `GET /api/inventory/`, raw inventory array with preferred/neutral food and a nonfood egg |
| `inventory-empty.json` | Same inventory endpoint with no owned items; raw empty array |
| `pet-feed.json` | `POST /api/pets/51/feed/`, preferred food consumed and growth confirmed |
| `pet-feed-neutral.json` | Same pet with neutral food; final food quantity consumed |
| `pet-feed-evolved.json` | `POST /api/pets/52/feed/`, growth capped at 100 and newly created mount ID confirmed |
| `pet-activate.json` | `POST /api/pets/52/activate/`, confirmed active pet with nested species/potion |
| `mount-activate.json` | `POST /api/mounts/62/activate/`, confirmed active mount with nested species/potion |
| `pet-feed-missing-food.json` | Feed rejected with HTTP 400 because `food_item_id` is absent |
| `pet-feed-unavailable-food.json` | Feed rejected with HTTP 400 because the child does not own that food |
| `pet-feed-already-evolved.json` | Feed rejected with HTTP 400 because the pet has already evolved |
| `pet-not-owned.json` | Foreign or unknown pet feed/activation rejected with the same HTTP 400 body |
| `mount-not-owned.json` | Foreign or unknown mount activation rejected with the same HTTP 400 body |
| `inventory-hatching.json` | `GET /api/inventory/`, owned eggs and hatching potions with quantities and nullable typed species/potion names |
| `pet-incubation-empty.json` | Self-scoped `GET /api/pets/incubations/`; no current egg, configured duration and server clock |
| `pet-incubation-start.json` | `POST /api/pets/incubations/`; HTTP 201 consumes one egg/potion with a UUID request ID; same-request retry returns the identical incubation with HTTP 200 |
| `pet-incubation-progress.json`, `pet-incubation-ready.json` | Real server-relative waiting/ready reads; neither creates an owned pet or grants rewards |
| `pet-incubation-too-early.json` | Explicit hatch before the accepted deadline returns HTTP 409 without writes |
| `pet-incubation-hatched.json`, `pet-incubation-hatch-retry.json` | Explicit ready hatch returns HTTP 201 with the full saved baby; exact-ID retry returns HTTP 200 and `freshly_hatched: false` |
| `pet-incubation-missing-ingredients.json` | Start rejects missing item IDs with typed field errors and HTTP 400 |
| `pet-hatch-retired.json` | Authenticated legacy `POST /api/pets/hatch/` returns HTTP 410 without spending ingredients |
| `pet-hatch-unavailable-egg.json` | Incubation start rejected with HTTP 400 because the child does not own that egg |
| `pet-hatch-unavailable-potion.json` | Incubation start rejected with HTTP 400 because the child does not own that potion |
| `pet-hatch-duplicate.json` | Incubation start rejected with HTTP 400 because the child already owns that species/potion combination, including an evolved pet |
| `expedition-start-short.json` | `POST /api/mounts/61/expedition/`, HTTP 201 two-hour run with locked planned loot |
| `expedition-start-standard.json` | Same start endpoint for mount 62, four-hour run with two planned item slots |
| `expedition-start-long.json` | Same start endpoint for mount 63, eight-hour run with three planned item slots |
| `expeditions.json` | `GET /api/expeditions/`, self-scoped raw `{expeditions: [...]}` envelope |
| `expeditions-ready.json` | `GET /api/expeditions/?ready=true`, only active, returned and unclaimed runs; negative remaining seconds |
| `expeditions-empty.json` | Same list endpoint with no matching owned rows |
| `expeditions-claimed.json` | Full history retains the claimed row even though its time-based `is_ready` remains true |
| `expeditions-expired.json` | Full history retains an expired row; the ready-only list excludes it |
| `expeditions-ready-claim.json` | Ready short-run context for normal, repeat, boosted and archived-item claim checks |
| `expeditions-ready-salvage.json` | Ready short-run context with a planned cosmetic the child already owns |
| `pets-stable-expeditions.json` | Stable mounts expose active expedition summaries with the same identities and locked loot |
| `pets-stable-expedition-rested.json` | After claim, the same mount cannot explore again until Django's next local midnight |
| `pets-stable-expedition-next-day.json` | The next server day permits another expedition without changing saved rewards |
| `expedition-claim.json` | `POST /api/expeditions/103/claim/`, committed first claim with actual base coins and planned item slots |
| `expedition-claim-repeat.json` | Same claim repeated, `freshly_claimed: false`, zero new coins and no writes |
| `expedition-claim-boosted.json` | Actual Lucky Coin award differs from the locked base coin preview |
| `expedition-claim-salvage.json` | Owned cosmetic converts to a separate salvage coin entry, annotated on its planned slot |
| `expedition-claim-archived-item.json` | Archived planned item stays in the response but creates no inventory; base coin award still commits |
| `expedition-invalid-tier.json` | Start rejected with HTTP 400 for missing or invalid tier |
| `expedition-mount-not-owned.json` | Foreign, sibling or unknown mount start rejected with the same HTTP 404 body |
| `expedition-not-owned.json` | Foreign, sibling or unknown expedition claim rejected with the same HTTP 404 body |
| `expedition-early-claim.json` | Claim rejected with HTTP 400 before the server return deadline |
| `expedition-already-active.json` | Start rejected with HTTP 400 while that mount has an active expedition |
| `expedition-daily-limit.json` | Start rejected with HTTP 400 after the same mount's first run is claimed that local day |
| `expedition-expired.json` | Expired run claim rejected with HTTP 400 and no awards |
| `pets-stable-breeding-retired.json` | Stable preserves historical `last_bred_at` and an active expedition while legacy breeding availability stays false and cooldown seconds stay zero |
| `mount-breed-retired.json` | Authenticated `POST /api/mounts/breed/` returns HTTP 410 without inspecting parent IDs or changing inventory, companions, history or rewards |

`config/tests/test_api_contract_fixtures.py` seeds fixed family/user/habit/skill
and companion/item IDs and a fixed clock, sends requests through the real Django
views, then compares the rendered JSON to these files. It also verifies token rotation, child/family
scope, pagination, persisted strength and XP, and duplicate-tap rejection. The
ordinary tap runs the real game loop with fixed random input; only the no-event
scenario replaces that optional service boundary with `None`. Date of birth and
school grade are unset to avoid date-dependent computed identity values. The
companion checks use typed food species, verify food consumption, growth and
evolution persistence, and ensure pet/mount activation remains exclusive. Both
sibling and foreign-family companion IDs are rejected without changing either
owner's state. Evolution uses the real service and a test-table sequence reset
to keep the newly generated mount ID deterministic on PostgreSQL/SQLite and
test-suite ordering. Inventory is an unpaginated array; its inventory-entry IDs
are distinct from the item-definition IDs submitted to the feed endpoint.

Owned pet and mount responses include the read-only nested `species.slug`,
alongside species ID and sprite key, for exact companion appearance bindings.
Hatch/activation responses and stable/mount reads carry the same saved identity
through evolution; a sprite filename never substitutes for species identity.
Legacy species without an authored slug return explicit `null` and keep their
existing 2D presentation.

Timed incubation starts at `POST /api/pets/incubations/` with item-definition
`egg_item_id`, `potion_item_id` and a UUID `request_id`. It consumes one owned egg
and one compatible potion exactly once, freezes their display/species/potion
identities and an absolute deadline, and creates no `UserPet`, badge or Chronicle
first. Same-request retries return the saved row; a conflicting request cannot
occupy the account's single active slot. The default duration is 24 hours
(86,400 seconds); these canonical examples use that default and claim at the
saved `ready_at` deadline.

`GET /api/pets/incubations/` returns `{incubation, duration_seconds, server_now}`.
The nullable row carries frozen ingredient and family metadata, `started_at`,
`ready_at`, nonnegative integer `remaining_seconds`, boolean `is_ready`,
`status: incubating|ready|hatched`, nullable `hatched_at` and nullable `pet_id`.
Its deadline and readiness use the same server clock snapshot. Merely reading
at or after readiness creates no pet and grants nothing.

Only an explicit ready `POST /api/pets/incubations/<id>/hatch/` creates the full
inactive baby and its normal badge/Chronicle effects. Its envelope is
`{incubation, pet, freshly_hatched, server_now}`; the first success is HTTP 201.
An exact-ID retry is HTTP 200 with the same pet and `freshly_hatched: false`,
without consuming more supplies or paying again. Start returns
`{incubation, server_now}`. Early/conflicting actions return HTTP 409; foreign,
sibling and unknown incubation IDs share HTTP 404. All routes require auth.
The old instant `/api/pets/hatch/` is retired with HTTP 410 and no writes.

Producer checks exercise the real start, waiting and ready reads, early rejection,
explicit claim and retry. They pin generated IDs on PostgreSQL/SQLite, retain the
prior active companion, preserve sibling/foreign inventory, and verify no pet or
first-hatch entry exists until the ready claim. Existing duplicate and ingredient
validation fixtures now come from start. Typed inventory names and saved lifecycle
stages retain their existing meanings. `pet-hatch.json`, `pet-hatch-roster.json`
and `pet-hatch-missing-ingredients.json` are retained historical instant-hatch
snapshots for older reference material; active clients use the incubation fixtures.

Expeditions remain self-scoped to the authenticated account, including siblings
within one family. Start submits only `tier`; claim uses the expedition ID in the
path with an empty POST body. Start and list never award coins or inventory.
Tier durations, return timestamps and readiness come from Django. Remaining
seconds are signed and become negative after the return deadline; `is_ready`
is a time property even on claimed or expired history. A claimable row must have
both `status: "active"` and server-confirmed readiness. Listing is an unpaginated
envelope, and `ready=true` excludes claimed and expired history.

Loot is rolled once at start with fixed random input in these producer checks.
Its item slots can repeat the same item ID, especially on longer runs; these
slots are distinct from inventory's unique item entries. Claim commits the
actual base coin award and inventory changes together. `coins_awarded` includes
Lucky Coin's multiplier, while duplicate cosmetic salvage is a separate ledger
entry indicated by `salvaged_to_coins` on the slot. The returned `items` remain
the planned display snapshots: an item archived after start can be skipped by
materialization while its slot remains in the receipt. Clients must refresh
inventory and balance rather than treating every planned slot as proof of
ownership or summing planned coins as a new award. Repeat claims preserve the
slots with `freshly_claimed: false` and `coins_awarded: 0` and award nothing again.

The expedition producer checks run the real post-commit game loop exactly once
with `drops_allowed: false`, verify unchanged rewards during reads/start and
rejections, and compare persisted inventory, coin ledger, drops, skill XP,
streak and notifications before/after a repeated claim. The local-day start cap
still applies after claiming, and sibling/foreign-family rows never enter an
owned list or become eligible for start/claim. Real endpoint-created expedition
IDs are pinned with a test-table sequence reset for PostgreSQL and SQLite.

Breeding has been removed. Every current mount response retains the read-only
compatibility fields `can_breed: false` and `breeding_cooldown_seconds: 0`;
the stable envelope retains `breeding_available: false`. Saved `last_bred_at`
values remain historical data, including on activation responses. Reads do not
rewrite those timestamps or make breeding available after a former cooldown.

Mount responses also include read-only `expedition_available` and
`expedition_available_at`. Availability is true only with no active/unclaimed
trip and no expedition started that Django local day, including claimed or
expired trips. A claimed trip from today receives the next local midnight as
an ISO timestamp; an available mount or an unclaimed trip receives null.
`expedition_available_in_seconds` is the server-relative wait until that
midnight, zero when available and null for active/unclaimed trips. It lets a
client schedule its next refresh without trusting the device clock.
The current Django timezone defines that day, matching the start service;
family and phone clocks do not alter it. Reads grant no rewards and never claim
a returned trip. Clients may refresh at a deadline or on resume, but start and
claim remain explicit server-authorized actions.

Authenticated `POST /api/mounts/breed/` returns HTTP 410 with
`{"error": "Pet breeding has been removed."}` for valid, missing, malformed,
same-mount, unknown and other-family IDs. It never processes parents, grants
items or rewards, stamps history or changes existing expeditions. Authentication
remains required. The React transport checks preserve that retirement response
without replaying a stale client's POST; the current application exposes no
breeding action or API wrapper.

The broader hatch scenarios in `test_api_contract_fixtures.py` use an explicit
scoped synthetic asset policy to exercise ingredient compatibility. They do not
advertise those identities as production art.
`test_catalog_api_contract_fixtures.py` uses the production default: retained
`chick` / `cute-chick` plus 14 exact `meshtint-*` families, all Base-only, with
explicit server lifecycle rules. It seeds supported and unavailable saved rows,
compares real catalog/stable/inventory responses, verifies rejected hatch/equip
requests consume nothing, and confirms even two supported grown companions cannot
breed. `frontend/src/api/catalogContractFixtures.test.js` consumes the current
bodies through the real API wrappers and preserves rejection status/details.

The former success/cooldown snapshots `pets-stable-breeding.json`,
`pets-stable-breeding-after.json`, `mount-breed.json`,
`mount-breed-chromatic.json`, `mount-breed-fallback.json`,
`mount-breed-missing-mounts.json`, `mount-breed-same-mount.json`,
`mount-breed-invalid-ids.json`, `mount-breed-not-owned.json`,
`mount-breed-cooldown.json` and `mount-breed-repeat-cooldown.json` are retained
only because retired Unity reference checks read those files. They are
historical snapshots, not current endpoint contracts or supported gameplay;
active Django producers and React consumers use the retirement fixtures above.
Retired Unity reference checks are not release gates and may reflect former
eligibility rules in the other snapshots they read.

Read-only `catalog_available` on species, potions, owned pets/mounts and items
describes new catalog eligibility. Stable ownership/totals retain saved legacy
rows, while supported progress uses `total_possible`. Saved pet
feeding/activation/evolution and mount expeditions remain available. Cosmetic catalogs retain all slot keys with an empty
`active_pet_accessory` list; inventory retains earlier accessories without
equip actions. A previous accessory selection can still be removed. Flags
never prove a reward happened or authorize a mutation locally.

`config/tests/test_greenlight_api_contract_fixtures.py` sends the payout,
snapshot, preview and reconciliation requests through their real views with a
fixed clock and synthetic families. It verifies persisted negative payout ledger
entries, paid timecard state, no writes during preview, statement matching without
another payout, and duplicate-safe reconciliation retries. Cross-family overview
access is rejected. Endpoint-created identities are deterministic on SQLite and
PostgreSQL. No Greenlight API or real bank account is contacted.

Greenlight workflow monetary amounts are decimal strings with two places.
`owed_balance` is the app's outstanding payment ledger balance;
`approved_payable` excludes pending or disputed hourly credits and is clamped
at zero. `pending_hourly` identifies that unapproved portion. These amounts are
separate from `balance_snapshot`, a parent-reported external observation with
`amount` and `as_of`, or explicit JSON `null` when unknown. Paying or reconciling
work changes debt but never estimates an external bank balance. Payout response
amounts are positive transfer amounts; the corresponding payment ledger entries
are negative. A statement preview returns signed decimal amounts, so purchases
remain visible for review without becoming eligible payouts.

The statement contract uses normalized CSV columns
`date,amount,description,reference,type`. Only positive rows explicitly marked
`type=transfer` can be selected. A preview's stable fingerprint is sent back with
the same CSV for server-side revalidation; a selected transfer may match an
existing ledger payout instead of recording a second one. This is a manual
statement workflow, not a claim that every Greenlight export has these columns.

`frontend/src/api/sharedContractFixtures.test.js` serves these same files with
MSW and exercises the real React API wrappers, token handling, list normalization
and HTTP error propagation, including feed/evolution, pet/mount activation, and
the complete ready-hatch receipt. Incubation checks assert the exact UUID and
ingredient request, server readiness, explicit claim/retry and legacy retirement
without automatically replaying a POST.
Notification page links are root-relative so an HTTP tunnel behind a public
HTTPS site cannot change the client's destination origin. Producer checks cover
HTTP, HTTPS and forwarded proxy headers, pagination in both directions, unchanged
unread state, and rejection of sibling/foreign-family acknowledgement. React and
Unity consume the same synthetic pages; Unity still rejects external, downgraded,
credential-bearing or repeating continuations.
Unity's `ApiContractValidation.Run` reads the files directly from this repository;
run it from a complete checkout, not an isolated
copy of `unity/AbbyCamp`.

## Check for drift

`config.tests.test_progression_api_contract_fixtures` produces
`progression-lab-metadata.json` and `progression-lab-report.json` through the
real staff-parent endpoints, using fixed synthetic global skill, item, drop,
companion, badge and challenge definitions. The report starts from zero and
contains no household progress. The React consumer
`src/api/progressionLabContractFixtures.test.js` checks the exact metadata and
anonymous simulation request/response shapes. Both run in the API fixtures
gate. See [Progression Lab](../../docs/operations/progression-lab.md) for the
model boundary, conditional milestone percentiles and finite-content subset.

`config.tests.test_homework_ai_api_contract_fixtures` produces family Planning AI
settings through real parent-only reads, saves and resets. The exact response
contains only `provider`, `model` and `has_api_key`; API keys are write-only and
the synthetic key never appears in fixtures. Coparents share a family connection,
other families remain independent, and children cannot read or change it.
`frontend/src/api/homeworkAIContractFixtures.test.js` consumes the same bodies,
checking authenticated GET/PUT calls, optional key omission and an empty DELETE.
PUT accepts `provider`, `model` and optional `api_key`. An omitted or blank key
retains the saved key only for the same provider; a provider change requires a
new key. `provider: "default"` or DELETE removes the family connection and
returns the disconnected sentinel `{provider: "default", model: "",
has_api_key: false}`. AI homework and project planning remain unavailable until
the family configures OpenAI or Claude; deployment credentials do not supply a
planning fallback. The settings URL is retained for compatibility. Saving
settings does not contact a provider or validate its key/model access.

`config.tests.test_project_ai_api_contract_fixtures` runs project planning through
the real endpoints and provider response parser, with only the provider network
mocked. Generation creates no project or plan rows. New-project drafts accept
`title`, optional `description`, `difficulty` and optional `guidance`, returning
`{plan, plan_version: null}`. A parent saves the reviewed arrays in `plan_create`
on the ordinary project-create request, so the project and its plan save together.
Existing-project drafts accept optional `guidance` and return the same `plan`
plus an opaque `plan_version`. Apply sends `{plan, plan_version}` and appends
the reviewed entries atomically; it preserves existing milestones, steps and
materials. A changed project or repeated application returns HTTP 409 without
further writes. Clients retain the version from generation and request a fresh
draft after a conflict.

Plans contain exactly `milestones`, `steps` and `materials` arrays. Each step's
nullable `milestone_index` refers to a milestone in that proposed array, rather
than a saved ID or an existing project milestone. Material `estimated_cost`
values are decimal strings; generated costs start at `"0.00"` and can be edited
before saving. Planning remains parent-only and within the authenticated family.
The producer verifies nonmutating drafts, reviewed creation, append/retry
behavior and scope. `frontend/src/api/projectAIContractFixtures.test.js` consumes
the same bodies and checks exact request routes, reviewed payloads, version
retention and conflict propagation through the API wrappers.

The same producer covers the boundary between homework planning and projects.
Project details include the read-only boolean `is_homework_plan` and nullable
integer `homework_assignment_id`. The boolean covers both the durable homework
marker and legacy assignment links; the assignment ID is returned only for a
link matching the project's assigned child and family. Ordinary projects return
`false` and `null`. These fields describe server-owned identity and cannot turn
a project into or out of homework through client writes.

Homework planning rows remain readable by their existing detail URL so the
assignment's `project` link still opens its steps. The ordinary project list
excludes them for both parents and children. Homework submission, proof and
approval stay on the original assignment; its plan supplies structure rather
than a second paid task. Clock-in rejects a homework plan with HTTP 400 and
creates no time entry. Shared fixtures exercise an existing link whose durable
marker has not been set, preserving this boundary for older homework too. React
consumes those same list, detail, assignment and rejection bodies through the
normal API wrappers.

`config.tests.test_drive_export_api_contract_fixtures` exercises the real source
list and stored-file upload endpoints with synthetic files and only Google's
network mocked. `frontend/src/api/googleDriveContracts.test.js` consumes the
same pages and upload receipt through the real API wrappers. Both are included
in PR API validation. Unity is retired and consumes neither parent-only endpoint.

From the repository root, with the normal backend test environment configured:

```sh
python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures config.tests.test_greenlight_api_contract_fixtures config.tests.test_avatar_api_contract_fixtures config.tests.test_rpg_integrity_api_contract_fixtures config.tests.test_catalog_api_contract_fixtures config.tests.test_catalog_icon_api_contract_fixtures config.tests.test_report_card_api_contract_fixtures config.tests.test_challenge_api_contract_fixtures config.tests.test_homework_ai_api_contract_fixtures config.tests.test_project_ai_api_contract_fixtures
```

For Docker-less checks, use a disposable SQLite `DATABASE_URL` such as
`sqlite:///:memory:` and a synthetic `SECRET_KEY`. Do not use a production DB.
From `frontend/`:

```sh
npm run test:run -- src/api/sharedContractFixtures.test.js src/api/avatarContractFixtures.test.js src/api/rpgIntegrityContractFixtures.test.jsx src/api/catalogContractFixtures.test.js src/api/reportCardContractFixtures.test.js src/api/challengeContractFixtures.test.js src/api/homeworkAIContractFixtures.test.js src/api/projectAIContractFixtures.test.js
```

For retired-reference checks only, run Unity with `-executeMethod AbbyCamp.Editor.ApiContractValidation.Run`, or use
**Abby Camp → Validate API Contracts** in the Editor. See the Unity README for
the pinned editor and batch-mode commands.

## Update an intentional API change

Review the server and affected React consumers first. Regenerate only through the
backend suite so sample payloads cannot drift into invented shapes. In PowerShell,
after configuring the test environment:

```powershell
$env:UPDATE_API_CONTRACT_FIXTURES = '1'
try {
    python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures config.tests.test_greenlight_api_contract_fixtures config.tests.test_avatar_api_contract_fixtures config.tests.test_rpg_integrity_api_contract_fixtures config.tests.test_catalog_api_contract_fixtures config.tests.test_catalog_icon_api_contract_fixtures config.tests.test_report_card_api_contract_fixtures config.tests.test_challenge_api_contract_fixtures config.tests.test_homework_ai_api_contract_fixtures config.tests.test_project_ai_api_contract_fixtures
} finally {
    Remove-Item Env:UPDATE_API_CONTRACT_FIXTURES
}
```

Review the JSON diff and adapt the React consumers/tests as needed.
Then rerun backend and React checks with regeneration disabled. CI compares snapshots
and refuses regeneration. An unexpected added, removed, renamed or retyped field
fails the backend comparison even if a client silently ignores it.

Unity currently leaves payment actions in the parent web app. Its Editor-only
Greenlight fixture checks still verify decimal-string amounts, explicit unknown
balance, the external observation timestamp, and reconciliation outcomes. These
checks do not add a runtime banking client or include fixtures in player builds.

## Material readiness and purchase records

Material responses include the read-only boolean `is_ready`: a material is
ready when it is on hand or has been purchased. Existing purchases remain ready
without a backfill. `POST /api/projects/<project>/materials/<material>/mark-ready/`
accepts an empty JSON object and records only that the supply is on hand. It
does not set `is_purchased`, `purchased_at`, `actual_cost` or `reimbursed`, and
does not replace the estimate. The matching `mark-not-ready/` action also takes
an empty object and clears only the on-hand mark; a saved purchase still makes
the material ready and retains its purchase date and actual cost. Both actions
can be repeated safely. The existing `mark-purchased/` action remains
available for actual purchases with an optional `actual_cost`; an explicit
`"0.00"` remains zero. Estimates and readiness alone are not actual spending.

`config/tests/test_material_api_contract_fixtures.py` produces all material
fixtures through real child-authenticated endpoints with fixed identities and
timestamps. It checks saved state, repeat readiness calls, the shared MCP
material projection and rejection of another family's write.
`frontend/src/api/materialContractFixtures.test.js` consumes those exact bodies
through `getMaterials`, `markMaterialReady`, `markMaterialNotReady` and `markPurchased`, checking request
verbs, paths, payloads, decimal strings and rejection propagation. Run both
modules with the standard backend and frontend test commands above; regenerate
the fixture producer only for an intentional API change.

## Color-theme display names

Item `name` and flattened `item_name` fields project the current Meadow color-theme
label for known `cosmetic_theme` metadata, including legacy seasonal palette keys.
The canonical labels and aliases live in `shared/catalog/theme-presentation.json`.
Stored names, IDs, palette keys and verified artwork bindings remain unchanged;
unknown themes and other catalog names retain their saved labels. New reward
snapshots use the current label, while already frozen outcomes remain intact.
Theme `type_display` is “Color theme”. The inventory appearance fixture covers
the current label and original artwork identity together.

## Saved Archer appearance

Character responses also contain `avatar_configuration`:
`{avatar_id, appearance, accessories}`. Appearance keys belong to the selected
base; accessory keys are shared logical slots (`headwear`, `face_accessory`,
`left_hand`, `right_hand`, `back`). Their values are global item IDs or `none`.
The separate `CharacterProfile.avatar_configuration` JSON field defaults to
`{}`. Existing profiles project their saved Archer choices when that field is
unsaved, without a backfill or persisted read. A nonempty saved configuration
is returned unchanged, including a previously available base or item missing
from the current catalog. Clients show unavailable presentation and permit an
explicit change; they must not replace that saved body with another avatar.

`GET /api/character/avatar/catalog/` returns schema version 1, a
`default_avatar_id`, ordered `accessory_slots`, an `accessories` map and ordered
`avatars`. Shared item metadata contains its display label and public source-pack
ID. Source provenance is not a compatibility or earned-ownership rule. Each base
defines its own appearance defaults, groups/fields/choices, shared-slot defaults,
presets and `accessory_bindings`. Accessory choices reference the shared registry
with `accessory_id`; their labels come from that item. Per-base bindings contain
the supported `item_ids`, the reviewed attachment and an optional
`legacy_preference_key` for the Archer adapter. The default Archer currently has
no right-hand items. Only the prepared Archer and its nine shared pieces are
offered. Synthetic tests reuse the same Archer bow/quiver IDs on a separate
Knight definition with independently declared sword/shield bindings; no Knight
art or availability is claimed.

`POST /api/character/avatar/configuration/` accepts exactly
`{avatar_configuration: {avatar_id, appearance, accessories}}` and returns the
complete character. The base ID is required. Omitted appearance/accessory values
use its declared defaults. Unknown fields/types, unregistered bases, and items
outside that base's explicit slot bindings are rejected without writes. A base
switch can retain shared pieces when fitted to both bases; carrying an unfit
item ID is rejected rather than silently dropping it. Omitted slots reset to
`none` under the full-replacement contract. All writes remain
authenticated, self-only, locked and independent of inventory/rewards. Repeating
the same canonical configuration changes no timestamp and does not materialize
an already equal default projection. The companion GET returns the same character.
Both catalog/configuration GETs ignore only the client's noncredential
`_abby_session` cache namespace; other queries (including account targeting)
are rejected. Both POST endpoints reject all query parameters.

The existing flat `avatar_preferences` and POST contract below remain available.
A generic Archer save synchronizes that flat projection. The legacy POST
explicitly selects Archer and synchronizes the generic configuration; an equal
legacy retry does not persist an otherwise unsaved generic field. Other bases
retain the last Archer projection for older clients, while current clients use
`avatar_configuration` as the selected presentation. Future bases require actual
prepared artwork, their own reviewed renderer/attachment adapter and registered
appearance/binding definitions. A source-pack name or catalog entry alone does
not establish fit or public-runtime approval.

`config/tests/test_avatar_api_contract_fixtures.py` produces the avatar fixtures
through the real authenticated character endpoints. `avatar_preferences` contains
`hair_style` (`hair-01` through `hair-04`), `hair_color` (`light`, `dark`, `brown`,
`orange`, or `grey`), `skin_tone` (`fair` or `tan`), `outfit` (`aqua`, `nature`,
`fire`, or `dark`), `outfit_style` (`archer-01` through `archer-03`),
`face_style` (`face-01` through `face-03`), and `head_style` (`head-01` or
`head-02`, rounded/pointed ears). Default options are `hair-01`, `dark`, `fair`,
`nature`, `archer-01`, `face-01`, and `head-02`.
Four optional wardrobe fields are also saved: `headwear_style` (`none`,
`crown-eve`, or `hood-mystical`), `mask_style` (`none` or `mask-undercover`),
`bow_style` (`none`, `bow-greenhorn`, `bow-vines`, or `bow-myth`), and
`quiver_style` (`none`, `quiver-angel`, `quiver-rook`, or `quiver-tale`).
Each wardrobe field defaults to `none`. These are presentation selections;
saving them does not acquire, equip or unlock gameplay inventory.
Reads normalize older empty or malformed stored options without writing to the
profile. Legacy four-option looks retain their selected hair, skin and palette
and project `outfit_style: archer-01`, `face_style: face-01` and
`head_style: head-02` without changing stored preferences. Older seven-option
looks retain their entire identity and receive all four wardrobe defaults
without a persisted read. Existing `outfit` palettes coordinate wardrobe art;
there is no separate wardrobe palette in the API.

`POST /api/character/avatar/` accepts exactly `{avatar_preferences: {...}}`.
Each save replaces the full appearance: omitted options reset to defaults, and
an empty preference object resets all eleven options. Unknown body/option fields,
invalid types/values, and query parameters are rejected. The endpoint only changes
the authenticated account's preferences and timestamp; it cannot target another
account, equip or grant inventory, change a trophy, or award XP/Coins. Repeating
the same normalized appearance changes nothing, including the saved timestamp.
The response is the complete character body, and later character reads retain
the confirmed appearance. These choices remain independent from gameplay
ownership or earned cosmetic slots. Rendering needs the corresponding reviewed
private runtime release; a legacy static release cannot substitute another look
for an expanded choice. Idle playback is local presentation, not an API award.

Run the producer and permission/state tests with a disposable test database:

```sh
python manage.py test --settings=config.settings_test apps.rpg.tests.test_avatar config.tests.test_avatar_api_contract_fixtures config.tests.test_rpg_integrity_api_contract_fixtures
```

## Automatic challenges and measured movement

`config/tests/test_challenge_api_contract_fixtures.py` creates a parent-authored
running goal through the actual API and logs two real movement sessions. A
separate eligible catalog goal advances without a pin. The second session
completes both goals after the distance goal has been unpinned. Producer checks
verify actual Coin ledger and skill progress, one automatic daily bonus, UUID
retry safety, family isolation and unchanged rewards after reading the list.
The same module runs actual pre-feature-to-current and `quests.0006` to `0007`
migrations in disposable subprocesses. It verifies saved legacy quests, co-op
participants, daily promises, paid/unpaid goal windows, contributions, receipts,
inventory, Coins, skill XP and movement counters remain intact without payouts
or invented distance. Retirement backfills private catalog origin and frozen
name/type, leaves parent goals outside catalog history, and permits deletion of
the original template while keeping saved goal promises. The public origin label
uses that saved marker; the underlying catalog identity/history fields stay private.

`GET /api/challenges/` returns `results`, the nullable `pin`, completed goal
`recent_receipts`, saved activity `challenge_receipts`, and `daily_bonus`.
Both receipt arrays use newest-first order, with descending saved row ID
breaking equal timestamps; ended history uses the same rule for equal deadlines.
Activity goal deltas follow the underlying goal records in ascending saved
identity order; their public IDs continue to identify occurrences.
Parents may select a same-family child with `user_id`; children cannot use that query to
read another account. Goal IDs identify occurrences (`goal:1`), not catalog
definitions. Retained legacy rows use `legacy:91`. Each goal reports server-owned
`origin: parent|catalog|legacy`; catalog origin survives template retirement and
legacy rows retain `legacy` regardless of their original author. Clients can group
these for presentation without inferring origin from a name or pin. `target` and `progress` are
decimal strings. Goal status is `upcoming`, `active`, `completed` or `expired`.
New catalog goals receive their full window on first automatic offer/evaluation,
subject to cutover, template creation, badge and legacy cutoffs. Pending eligible
saved work can anchor the first window; processed history does not replay, and
later reads/pins never reset an existing window or paid receipt.
`starts_at` and `ends_at` define the server window; `what_counts`
describes the activity filter and catalog eligibility. Catalog planning says
“planned homework (first per day)” and catalog creation says “logged creations
(first two per day)”; parent-created goals count all valid matching records.
The eligibility flag is private server state and is never authorable through the
API. The action may include a movement type ID.

Catalog image IDs are presentation only. `catalog_icon` is an approved asset ID
or null, resolved by Django from `shared/catalog/icon-bindings.json` using exact
item slug/name/type, system challenge name/type, or Chick slug/name/sprite identity.
Species also expose `grown_catalog_icon` for the catalog portrait. Flattened
drop and reward rows expose `item_catalog_icon`. Unknown or changed identities
retain null and the existing sprite/emoji fallback; clients must not infer a
binding from a sprite key or display name. The sixteen inferred consumable
entries preserve their confirmation flag and require each actual receiving
record to match. These fields grant no ownership, availability or progression.
Automatic goal art uses its retained catalog definition; parent goals and
catalog goals whose definition was removed return null. Purchased image bytes,
manifest object paths and reader credentials are absent from these responses.

`rewards` is the frozen preview. `reward_receipt` identifies the occurrence and
reports `pending`, `awarded` or `legacy`, actual `coins_awarded`/`xp_awarded`, and
a nullable `awarded_at`. Clients must not add either the preview or a replayed
receipt to a balance. Awarded automatic receipts also expose persisted `items`
outcomes as `{item_name, item_catalog_icon, quantity}` rows for new awards;
earlier saved receipts may omit the presentation ID. An egg converted to Coins additionally
has `salvaged_to_coins`; that amount is already included in `coins_awarded`, and
the row is not a delivered inventory item. Skipped unavailable items are absent
from the outcome list. Pending and retained legacy receipts omit actual item
outcomes. Clients show the frozen preview before award and recorded outcomes
after award. `POST`/`DELETE /api/challenges/<id>/pin/` returns only the
saved `{pin: <id|null>}` preference and cannot grant progress or rewards.

Parent `POST /api/challenges/goals/` accepts the child, activity trigger, optional
movement type, metric, target, unit, period and reward configuration. A stable
optional `request_id` UUID makes identical parent-save retries return the same
occurrence; changing details under that UUID returns HTTP 409. Weekly
goals use the family's Monday-to-Sunday window, and `repeat_weekly` retains
separate occurrences. Explicit midweek weekly creation includes existing saved
matching work in that week and may complete immediately. XP rewards require
skill tags. Nonpositive/fractional action targets and mismatched metric/units are
rejected before saving.

Movement saves accept optional decimal `distance`, `distance_unit: mi|km`, and
`client_request_id`. The response preserves decimal-string `distance_meters`,
display-unit `distance`, the UUID and saved activity receipts. A receipt wraps
all matching goal deltas in `goals` and an optional newly paid `daily_bonus`.
Display-unit distance rounds to the accepted three fractional digits and removes
trailing zeros; goal contributions and totals use three-decimal `ROUND_HALF_UP`
before persistence and completion checks.
Repeating the same UUID and identical input returns the existing session and its
original receipt; conflicting input is rejected. Old sessions return null
distance and gain no invented mileage.

The daily bonus payload exposes the server date/timezone, cumulative minutes,
completion/award flags, base Coins/XP, actual awarded amounts, period end and a
nullable receipt identity. Its day uses the family-local accepted/saved timestamp;
weekly goal progress keeps the original work day. Completed legacy settlement
retains its promised original date. Daily Coins keep Lucky Coin eligibility; goal Coins
keep the legacy quest policy. XP receipts use the actual weighted skill credit,
including existing rounding and boosts. A daily award requires qualifying saved
work; opening Today is not a prerequisite or an award action.

The React consumer `frontend/src/api/challengeContractFixtures.test.js` reads
these exact server bodies through the shared API functions, verifies request
verbs/bodies and preserves decimal strings, all goal deltas and reward receipts.
See [automatic challenge operations](../../docs/operations/automatic-challenges.md)
for rollout and repair boundaries.

## Quarter and semester report cards

`config/tests/test_report_card_api_contract_fixtures.py` produces report card
responses through the real child-authenticated grade endpoints with fixed
families, identities, timestamps and PostgreSQL/SQLite sequence state. The React
consumer in `frontend/src/api/reportCardContractFixtures.test.js` reads those
same bodies through `writeGrade`, `getGrades` and `updateGradeEntry`, preserving
decimal strings, pagination, reward receipts and nested field errors.

Report cards remain Chronicle entries with `kind: "grade"`. Their result is
stored in `metadata.report_card`, while individual assignment/class results
continue using `metadata.grade`. To capture a card, submit `report_card` instead
of the single-result fields, plus the existing `client_entry_id`, optional
`reflection`, `occurred_on` and `is_private`. A card contains `period_type`
(`quarter` or `semester`), integer `period_number` (1–4 for quarters or 1–2 for
semesters), integer `school_year` (the starting year, 1–9998), and a `subjects`
array containing 1–30 subjects with distinct names (case-insensitive). Each
subject has a nonblank `subject` of at most 80 characters, `grade_format`, and
only its active marking fields: `score` for percentages, `score` and `possible`
for points, or `letter` for letters. Decimal values use the existing normalized
string format; subjects may use different marking formats within one card.

Corrections may supply individual period fields inside `report_card`; omitted
period fields and subjects remain unchanged. A supplied `subjects` array replaces
the entire list and must contain complete valid rows. Sharing-only changes
preserve the saved card. Cards use the same author-only correction, default
privacy and family sharing rules as other
grades. UUID retries return the current saved entry, including later corrections,
without creating another result or reward. Recognition follows the existing
once-per-save-day grade policy: multiple subjects do not multiply XP, and a
second report card or individual result that day receives a zero-XP
`daily_limit` receipt. The producer checks persisted skill progress and the
daily counter after replay, history reads and corrections; rejected nested
fields consume no eligibility.

All creature families share ordered `lifecycle_stages: ["egg", "baby", "middle", "grown"]`
on species/catalog/codex responses. Pet and mount `lifecycle_stage` is read-only:
Baby below 50 saved growth, Middle from 50 until confirmed evolution, and Grown
after confirmed evolution or for an owned mount. Egg items remain inventory
with `lifecycle_stage: "egg"`, item `slug` and `pet_species_slug`. Registered
roster eggs require exact slug, typed FK and canonical metadata agreement;
retained nonregistered legacy metadata fallback cannot rescue a conflict. Other
items return null for the stage/species fields. Hatching consumes the
existing egg+potion pair into a Baby at zero growth. No stage read grants
ownership, growth or currency. See [companion lifecycle](../../docs/operations/companion-lifecycle.md).

Pet and mount responses also retain compatible read-only `evolution_stage`: `chick`,
`fledgling`, `bird`, or null for other identities. Only exact
`chick` / `cute-chick` / `base` uses these stages. Persisted growth below 50
selects Chick, 50 or higher selects Fledgling until confirmed mount evolution;
confirmed evolved pets and owned mounts select Bird. Client stage fields cannot
grant growth, ownership, rewards or mount eligibility.

## Earned RPG progress and frozen shop promises

`config.tests.test_rpg_integrity_api_contract_fixtures` produces the character
progression and frozen redemption examples through authenticated endpoints.
Character responses add read-only integer `total_xp`, `xp_in_level`, and
`xp_needed_for_level`. The character uses the existing skill XP thresholds
across the sum of saved skill XP; this projection adds no XP or currency.
`xp_needed_for_level` is the width of the current level, rather than the
remaining XP. At the highest authored level it is zero and Profile shows
“Highest level”. Existing appearance saves preserve earned state.

A redemption's nested `reward` retains its requested `cost_coins`,
`fulfillment_kind`, `item_definition` and `item_definition_detail` even after
the parent edits the current offer. Its `coin_cost_snapshot` remains the
refund authority. Catalog requests still describe the current offer. The
producer checks actual inventory delivery, unchanged held Coins, and approval
retry safety. The React consumer `src/api/rpgIntegrityContractFixtures.test.jsx`
checks these same saved promises and renders the earned/maximum character
responses through Profile's existing frontispiece.

The same producer exercises a real parent co-op assignment and child habit tap
outside a surrounding test transaction. Completion pays the full configured
Coins, skill XP and supported items to every participant, including a child
with no contribution; the game event describes the finishing child's receipt.
The producer verifies each participant's persisted payout, keeps unrelated
families and the parent unpaid, and confirms later activity, completion retries
and a rejected nonrepeatable restart cannot repay the campaign. The React
consumer preserves that ordinary habit response and the restart error through
`logHabitTap` and `startQuest`.

## Reading books and reflections

`config.tests.test_reading_api_contract_fixtures` produces shelf, session,
correction, pagination, summary, discovery, family-suggestion and validation
responses through authenticated Django endpoints. The React consumer is
`frontend/src/api/readingContractFixtures.test.js`. All book titles, authors,
families and reflections in these fixtures are synthetic.

Books use `reading`, `want_to_read`, `finished` and `paused` statuses. Each
reading session belongs to one saved book and preserves its date, minutes,
pages, chapter/section, print/ebook/audiobook format, optional reaction and
optional family-visible reflection. Creates require a `client_request_id` UUID;
identical retries return the saved record, including subsequent corrections,
and changed payloads with the same UUID fail without adding another row.
PATCH cannot reassign the owner or book. Books with saved sessions cannot be
deleted until their sessions are explicitly removed.

Children access only their own reading; parents can select only a child in
their family using `user_id`. Summary dates use the household timezone. These
records are separate from private journal entries. New minutes logged for the
current household day advance a once-daily ten-minute reading reward. Print,
ebook and audiobook minutes count equally; reflections remain optional.
The summary's `reading_adventure` reports the target, credited/remaining minutes,
earned state, base 15 Reading Comprehension XP and 5 Coins, and actual payouts.
`reading-adventure-progress.json`, `reading-session-rewarded.json` and
`reading-summary-rewarded.json` show partial progress and a real boosted award
of 30 XP and 10 Coins. A session's nullable `reading_reward` identifies the
saved award on the log that crossed the threshold. Clients display this receipt
without adding it to balances locally. Replays, corrections, deletion and
historical logging never rearm the reward; retained daily progress and request
identities survive deleted logs. The producer checks the real XP and Coins
ledger after retries, corrections, deletion and a replacement log.
Saved book responses add `catalog_entry` or null. Catalog recognition normalizes
title/author case and whitespace; a blank legacy author is accepted only when
the title is unique. Recommendations use 64 bundled publisher-sourced books,
birthday age guidance when available and saved book interests/reactions.
Enriched entries include ISBN, nullable edition page count, verified formats,
moods/styles/themes, source links, cover URL and nullable
`series: {id, title, position}`. Ranking reads no reflections or invitation
messages and makes no runtime external metadata requests. Only the browser
loads Open Library covers, with no referrer and a missing-image fallback.
WorldCat links are catalog searches, not availability claims.

`GET /api/reading/recommendations/` accepts `interest`, `mood`, `style`,
`book_format`, `length`, `theme`, `q` (at most 160 characters), `similar_to`
(catalog ID), and `rotation` (0–1000). `book_format` avoids DRF's `format`
renderer parameter. Length boundaries are short ≤200, medium 201–349 and long
≥350 pages; unknown page counts are excluded by length filters. Search matches
catalog titles/authors/tags/series. Filters intersect, preserve age and shelf
boundaries, and series continuations require every earlier catalog volume to
be recognized on the reader's finished shelf. Rotation wraps through eligible
picks six at a time. Responses include `results`, `basis`, `total`, `has_more`
and `rotation`; each result includes `reason` and `reason_kind`.

`GET/POST /api/reading/discovery-feedback/` reads or updates preferences unique
to a reader/catalog ID. POST `choice` is `not_interested`, `already_read`, or
empty to clear the preference for Undo. Both nonempty choices hide the title
without creating shelf history, sessions or rewards. Parent calls select a
same-family child using `user_id`; child calls remain self-scoped.

`/api/reading-family-suggestions/` supports parent-only POST with child
`user_id`, `catalog_id`, optional `message` (500 characters maximum), and UUID
`client_request_id`. Identical retries return the existing invitation; changed
payloads or another sender reusing that child/UUID conflict. Responses include
the saved author-name snapshot in `suggested_by: {id, display_name}` (ID becomes
null if that parent is deleted),
`catalog_entry`, `status` and `on_shelf`. Access stays within the child's family;
surviving senders must still be parents in that family. GET lists only pending
invitations with standard pagination. PATCH accepts `status: dismissed` only.
Saving remains an explicit `/api/reading-books/` create: it changes `on_shelf`
without changing the pending invitation or awarding a reward.

`reading-discovery-picks.json`, `reading-discovery-book.json` and
`reading-discovery-feedback.json` cover metadata, filtered queries, catalog
recognition and preferences. `reading-family-suggestion.json`,
`reading-family-suggestions.json`, `reading-family-suggestions-saved.json` and
`reading-family-suggestion-dismissed.json` cover attribution, pending lists,
the child's explicit save, and dismissal. The existing Django producer and
React consumer above validate these synthetic responses together.

`inventory-roster-hatching.json`, `pet-incubation-roster-start.json` and
`pet-incubation-roster-hatched.json` cover real namespaced Base-only inventory,
accepted egg metadata and explicit ready-hatch producers/consumers. Ingredient items retain exact
catalog artwork; unrecognized item identities retain null and their existing
sprite/emoji fallback. Newly rolled expedition loot adds exact `catalog_icon`.
Previously saved loot and frozen receipts are retained verbatim. See the
[adoption runbook](../../docs/operations/companion-lifecycle.md).

Google sign-in/linking uses `google-auth-config.json` (public configuration),
`google-auth-init.json` (S256-bound authorization start), `google-auth-login.json`
(proof-verified login with the existing shared DRF token and UserSerializer),
`google-auth-linked.json` (confirmed link), and `google-auth-busy.json`
(HTTP 503 capacity refusal). The producer is
`config.tests.test_google_auth_api_contract_fixtures`; the React consumer is
`src/api/googleAuthContracts.test.js`. All tokens, Google identities and URLs
are synthetic. The browser sends the verifier only in the exchange POST;
callback URLs contain an opaque expiring ticket, never a DRF/Google token.
The global bound includes spent and expired rows until bounded cleanup removes
them. At capacity, a new start returns `code: authorization_busy` without saving
another verifier; retry requires capacity to become available.
See [the exchange contract](../../docs/operations/google-oauth.md#browser-bound-return-exchange).
