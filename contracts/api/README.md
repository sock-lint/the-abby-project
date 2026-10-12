# Shared API response fixtures

`fixtures/*.json` contains raw Django response bodies shared by the React tests
and Unity Editor API validation. Keep the files here rather than copying sample
payloads into each client. No production credentials or user data belong here.
The login token and all identities are synthetic and exist only in the test DB.

| Fixture | Endpoint / scenario |
| --- | --- |
| `google-drive-config.json` | `GET /api/auth/google/drive/config/`; public Picker configuration with synthetic keys |
| `google-drive-file.json` | `POST /api/auth/google/drive/file/`; verified metadata for a parent-selected school PDF, without credentials |
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
| `greenlight-overview-no-snapshot.json` | `GET /api/payments/greenlight/overview/?user_id=7`; money owed, approved payable and pending hourly earnings, with unknown external balance |
| `greenlight-balance-snapshot.json` | `POST /api/payments/greenlight/snapshot/`; parent-reported Greenlight balance with its observation time |
| `greenlight-overview.json` | Overview with a separately reported Greenlight balance; recording the observation changes no earnings or debt |
| `greenlight-payout.json` | `POST /api/payments/greenlight/payout/`; confirmed manual transfer pays an approved timecard exactly once |
| `greenlight-preview.json` | `POST /api/payments/greenlight/preview/`; match candidate, new transfer and excluded card purchase, without writes |
| `greenlight-reconcile.json` | `POST /api/payments/greenlight/reconcile/`; one existing payout matched and one new payout recorded |
| `greenlight-overview-reconciled.json` | Final overview after reconciliation; debt decreases, pending hourly earnings and balance observation stay separate |
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
| `pet-hatch.json` | `POST /api/pets/hatch/`, HTTP 201 full newly owned pet after consuming one egg and one potion |
| `pet-hatch-missing-ingredients.json` | Hatch rejected with HTTP 400 because either ingredient ID is absent |
| `pet-hatch-unavailable-egg.json` | Hatch rejected with HTTP 400 because the child does not own that egg |
| `pet-hatch-unavailable-potion.json` | Hatch rejected with HTTP 400 because the child does not own that potion |
| `pet-hatch-duplicate.json` | Hatch rejected with HTTP 400 because the child already owns that species/potion combination, including an evolved pet |
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
| `pets-stable-breeding.json` | Stable with two ready parents (including an away mount) and a third mount still on breeding cooldown |
| `pets-stable-breeding-after.json` | Same stable after a confirmed breed; both parents have their full server cooldown |
| `inventory-breeding.json` | Inventory confirms one added egg and potion while existing food and other quantities remain unchanged |
| `mount-breed.json` | `POST /api/mounts/breed/`, HTTP 201 registered egg/potion pair and cooldown receipt |
| `mount-breed-chromatic.json` | Same real endpoint with a supported Cosmic upgrade forced by fixed random input |
| `mount-breed-fallback.json` | Same real endpoint uses a registered supported potion when both old parents have incompatible variants |
| `mount-breed-missing-mounts.json` | Breed rejected with HTTP 400 when either parent ID is absent |
| `mount-breed-same-mount.json` | Breed rejected with HTTP 400 when both IDs identify the same mount |
| `mount-breed-invalid-ids.json` | Breed rejected with HTTP 400 when a parent ID cannot be parsed as an integer |
| `mount-breed-not-owned.json` | Sibling, foreign-family or unknown parent rejected with the same HTTP 400 body |
| `mount-breed-cooldown.json` | Breed rejected with HTTP 400 because one parent is still resting |
| `mount-breed-repeat-cooldown.json` | Repeating a completed breed during its cooldown is rejected without adding another pair |

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

Hatching also submits item-definition IDs, using `egg_item_id` and
`potion_item_id`. The real service consumes exactly one of each owned ingredient,
deletes a depleted inventory row, and returns a full new pet at zero growth that
is neither active nor evolved. It preserves the existing active pet and records
the first-hatch chronicle entry. Producer checks keep the generated pet identity
deterministic on PostgreSQL/SQLite, reject missing, unowned and wrong-type
ingredients without writes, reject duplicates even after evolution, and verify
sibling/foreign-family inventory remains untouched. A supplied `user_id` cannot
change the owner; unauthenticated requests are rejected. Typed inventory fields
`pet_species_name` and `potion_type_name` are display names or explicit null;
they do not expose catalog IDs or declare potion compatibility. The server
remains authoritative for ingredient eligibility. Nonempty species compatibility
lists are enforced before either ingredient is consumed; legacy empty lists
remain unrestricted. Stable `total_possible` sums those supported combinations
and uses all current potions for a legacy empty list. It does not multiply every
species by every potion when some combinations cannot hatch.

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

Every mount response now includes read-only `can_breed` and
`breeding_cooldown_seconds`. The latter is a nonnegative integer rounded up from
the remaining server cooldown; `can_breed` is exactly true when those seconds
are zero. Both fields use one server clock snapshot so a deadline passing during
serialization cannot produce conflicting values. An active expedition does not
change the existing breeding rule. A client must refresh eligibility rather
than authorize a breed from its own countdown.

Breeding submits distinct owned `mount_a_id` and `mount_b_id` values. The service
adds one registered egg and one potion to the authenticated account's inventory,
preserves both mounts, and stamps both parent cooldowns together. It consumes no
food, eggs, potions or parents and grants no coins, XP or bonus drops. Compatible
parental potions, registered compatibility fallbacks and supported Cosmic
upgrades use the catalog foundation's existing rules. The receipt contains item
identities, names/icons/sprite keys, selected species/potion names and nullable
slugs, `chromatic`, and `cooldown_days`; it does not hatch the resulting pair.
Producer checks compare the actual inventory changes, both cooldowns, unchanged
progression and other-family state, and rejection one microsecond before the
exact cooldown boundary. A later inventory/stable read confirms the new pair
and fresh cooldowns without repeating the non-idempotent POST.

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
the complete HTTP 201 hatch receipt. Hatching checks assert the exact ingredient
request and preserve the real rejection body/status without replaying a POST.
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

From the repository root, with the normal backend test environment configured:

```sh
python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures config.tests.test_greenlight_api_contract_fixtures
```

For Docker-less checks, use a disposable SQLite `DATABASE_URL` such as
`sqlite:///:memory:` and a synthetic `SECRET_KEY`. Do not use a production DB.
From `frontend/`:

```sh
npm run test:run -- src/api/sharedContractFixtures.test.js
```

Run Unity with `-executeMethod AbbyCamp.Editor.ApiContractValidation.Run`, or use
**Abby Camp → Validate API Contracts** in the Editor. See the Unity README for
the pinned editor and batch-mode commands.

## Update an intentional API change

Review the server and both client consumers first. Regenerate only through the
backend suite so sample payloads cannot drift into invented shapes. In PowerShell,
after configuring the test environment:

```powershell
$env:UPDATE_API_CONTRACT_FIXTURES = '1'
try {
    python manage.py test --settings=config.settings_test config.tests.test_api_contract_fixtures config.tests.test_greenlight_api_contract_fixtures
} finally {
    Remove-Item Env:UPDATE_API_CONTRACT_FIXTURES
}
```

Review the JSON diff and adapt the React and Unity consumers/tests as needed.
Then rerun all three checks with regeneration disabled. CI compares snapshots
and refuses regeneration. An unexpected added, removed, renamed or retyped field
fails the backend comparison even if a client silently ignores it.

Unity currently leaves payment actions in the parent web app. Its Editor-only
Greenlight fixture checks still verify decimal-string amounts, explicit unknown
balance, the external observation timestamp, and reconciliation outcomes. These
checks do not add a runtime banking client or include fixtures in player builds.
