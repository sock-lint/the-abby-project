# apps/pets/

Collectible pets + mount evolution + breeding + offline expeditions. Lifecycle: **Egg + Potion → Pet → Mount → Breeding**, plus the Finch-inspired Mount Expeditions loop.

## Active asset policy (October 2026)

New acquisition uses [`shared/catalog/asset-support.json`](../../shared/catalog/asset-support.json)
through `apps/rpg/catalog_support.py`. Production supports exact species slug
`chick`, sprite key `cute-chick`, and potion slug `base`. Chick is the pet;
The read-only server `evolution_stage` is Chick below 50 persisted growth, Fledgling from 50, and Bird after confirmed evolution at 100 or for its mount. Other identities return null. See [Bird adoption](../../docs/operations/bird-evolution.md).
The authored catalog remains in the database as generic engine/reference
content; owning a portrait or authoring a YAML row does not enable another
species, potion variant or 3D appearance.

Catalog/codex and potion choices intersect this policy with
`PetSpecies.available_potions`. Hatching rejects an unavailable pair or
ingredient before consuming inventory. Stable keeps every saved pet/mount,
adds read-only `catalog_available`, and counts only approved compatible pairs
in `total_possible`. React places unavailable rows in Saved collection while
retaining feeding, growth/evolution, activation and expedition controls.
Existing expedition history and locked loot remain claimable under the
existing rules; only newly rolled loot is restricted to available items.

Breeding requires two distinct supported owned parents, compatible approved
potions and registered available output items before cooldown/inventory writes.
`can_breed` also requires a ready supported partner; `breeding_available` is a
stable-level availability flag. The one Base Chick pair and unique ownership
constraints provide no production breeding pair today. Scoped
`RPG_ASSET_SUPPORT_POLICY` overrides in domain tests exercise broader mechanics
without changing the immutable production default. Preserve saved ownership
and permission boundaries when adding support; see
[`tests/test_asset_supported_catalog.py`](tests/test_asset_supported_catalog.py)
and PostgreSQL [`tests/test_catalog_concurrency.py`](tests/test_catalog_concurrency.py).

## Models
- `PetSpecies` (18 authored creatures, including Base-only Chick), `PotionType` (6 variants), `PetSpecies.available_potions` M2M declares compatible combinations.
- `UserPet` (growth 0-100, `last_fed_at`, `evolved_to_mount`, `consumable_growth_today` + `consumable_growth_date`), `UserMount` (`last_bred_at`).
- `MountExpedition` (offline adventure rows; `status`, `tier`, `started_at`, `ready_at`, `loot` JSON).

## Services
- `PetService` — `hatch_pet`, `feed_pet`, `evolve`, `set_active_pet`, `set_active_mount`, `breed_mounts`, `auto_grow_companions`, `happiness_for_pet`, `get_stable(user)` (returns dict with pets, mounts, totals for StableView).
- `ExpeditionService` (`apps/pets/expeditions.py`) — `start`, `claim`, `list_for_user`. `TIER_CONFIG` (short/standard/long). Exceptions: `ExpeditionError`, `ExpeditionNotFound`.

### Growth transactions

Food, direct consumables and passive Companion growth acquire the achievements
user `NO KEY UPDATE` gate before profile/pet/inventory writes. Growth Surge
locks its selected pet, as feeding and Feast already do. A concurrent feed and
surge preserve both consumed items' growth; a competing evolution cannot consume
food for an already evolved pet. Growth/Morale Tonic charges double preferred
and neutral feeds and decrement once with the successful food transaction;
failure preserves the charge and food. Boosted food does not use the direct
consumable daily cap.

Every growth path uses `PetService._save_growth` to save the growth/evolution
flag, obtain one matching mount, and emit the existing first-mount Chronicle and
family-scoped notifications. Feast therefore evolves a 90-growth pet immediately.
Mount creation failure rolls back growth, direct-growth cap and inventory.
Chronicle/notification failures retain their existing best-effort behavior within
savepoints. `apps/rpg/tests/test_consumable_progression.py` covers the real
authored tonic/food/Feast combination and shared skill-tonic consequences;
`test_consumable_concurrency.py` exercises real PostgreSQL growth overlap and
the shared user-before-profile/inventory/progress order.

### Daily expedition presentation (October 2026)

Every mount read/activation response carries `expedition_available`,
`expedition_available_at` and `expedition_available_in_seconds`. A mount is
available only with no active/unclaimed expedition and no expedition started
that Django local day. Claimed and expired runs still use today's allowance.
When that allowance is used, the timestamp names the next local midnight and
the integer gives a rounded-up server-relative wait. Available mounts return
null/zero; active trips return null/null because collecting the return requires
an explicit claim first. These read-only fields match `ExpeditionService.start`
and do not change its rules. Use the current Django timezone, independently of
family or phone settings. Readiness, remaining seconds and availability share
a server snapshot; serialized reads never claim a trip or award anything.

`DailyExpeditionCard` presents ready, away, returned and explored-today states
on both Companions' grown Bird home and Grown pets. The card opens the existing
duration sheet or explicitly claims the returned trip. Canvas greetings remain
local play and cannot start or claim expeditions. `useExpeditionRefresh`
reconciles on focus/visible resume and schedules a refresh from server-relative
return/day seconds; a timer never declares a claim or locally changes eligibility.
Rounded-zero waits are bounded to prevent tight retry loops. Owned collection
tiles also suppress a second same-day launch without removing saved legacy
mount journeys.

Feed, activation, launch and claim receipt callbacks use
`usePetMutationGuard` to prevent duplicate concurrent clicks and ignore results
after navigation or credential replacement. Successful feeds may trigger a
friendly local reaction; only `freshly_claimed: true` starts the return ceremony.
Refresh inventory/balance after confirmed claims rather than interpreting the
planned loot as new ownership. Shared wire fixtures cover resting and next-day
stable states; `test_expedition_eligibility.py` covers local midnight, unclaimed
returns, snapshot consistency and sibling isolation. No new play counters,
check-in rewards, XP or growth rules are introduced by these interactions.

## Endpoints
- `POST /api/mounts/breed/ {mount_a_id, mount_b_id}` — breed two mounts.
- `POST /api/mounts/<id>/expedition/ {tier}` — start an expedition.
- `GET /api/expeditions/[?ready=true]` — list user's expeditions.
- `POST /api/expeditions/<id>/claim/` — claim returned loot.
- `GET /api/pets/companion-growth/recent/` + `POST /api/pets/companion-growth/seen/` — companion auto-grow queue.

## Gotchas

- **Potion compatibility** (October 2026): hatching checks a species's nonempty `available_potions` before consuming ingredients. The loader populates omitted lists with all current potion types; an empty legacy relation means unrestricted authored compatibility, still intersected with the active asset policy for new hatching/breeding. Chick accepts Base only and prefers Birdseed food. Its licensed Chick / Fledgling / Bird appearances describe one species with server-derived growth stages, not three ownership identities. Fledgling at 50 adds no reward or mount; the existing 100-growth evolution remains authoritative. Existing species, owned pets, mounts and inventory remain intact on repeated content loads. [`test_cute_chick_catalog.py`](tests/test_cute_chick_catalog.py) covers the additive catalog, preservation and lifecycle rules.

- **Pets & mounts**: Lifecycle is **Egg + Potion → Pet → Mount → Breeding**. `PetService.hatch_pet` consumes one egg item and one potion item from `UserInventory`, reads `egg.pet_species` and `potion.potion_type` FKs (falls back to the legacy `metadata["species"]`/`["variant"]` strings for unmigrated rows), enforces one pet per `(user, species, potion)` combo, and creates a `UserPet` with `growth_points=0`. `PetSpecies.available_potions` M2M declares which species × potion combos are valid (defaults to all potions when unspecified in a content pack). `PetService.feed_pet` consumes a food item, stamps `UserPet.last_fed_at`, and adds growth — +15 if `food.food_species == pet.species` (preferred, FK-driven), +5 otherwise (neutral). **Consumable growth daily cap** (2026-04-23): direct-grant consumables `growth_surge` (+30 to active pet) and `feast_platter` (+10 to every unevolved pet) route through `UserPet.apply_consumable_growth(amount)` which enforces `CONSUMABLE_GROWTH_DAILY_CAP=50` per pet per local day. `growth_surge` returns `{growth_requested, growth_added, growth_capped, ...}` so callers can see when the cap clamped the boost; `feast_platter` returns a per-pet array. Tonic-doubled feeds are NOT capped — they require food items to exist, which is a natural limiter. Without the cap, hoarded consumables could fully evolve a pet (0 → 100) in a single sitting; the design intent is real-world weeks of bonding. Pinned by `ConsumableGrowthDailyCapTests` in [`apps/rpg/tests/test_new_consumable_effects.py`](/apps/rpg/tests/test_new_consumable_effects.py). At `growth_points >= 100`, the pet auto-evolves: `UserPet.evolved_to_mount=True` and a matching `UserMount` row is created (the original pet is retained in the stable). Only one `UserPet` and one `UserMount` can be `is_active=True` per user at a time — `set_active_pet`/`set_active_mount` deactivate any current one in the same transaction. Dashboard displays the active pet with a growth bar.

- **Companion species** (`slug=companion`) is a slow-burn pet that grows passively via `PetService.auto_grow_companions` on daily check-in; [`Companions.jsx`](/frontend/src/pages/bestiary/party/Companions.jsx) surfaces a "grows on its own — every daily check-in adds a little" line on the pet card so the mechanic isn't invisible. **Companion auto-grow surface** (2026-05-09): `auto_grow_companions` returns an `events` list (one entry per pet with `growth_added`, `new_growth`, `evolved`, `mount_id`, plus species/potion display metadata) and persists the same events to `CharacterProfile.pending_companion_growth` (JSONField — accumulates across un-seen ticks so a returning user catches up on every day they missed). Two endpoints expose the queue: `GET /api/pets/companion-growth/recent/` returns it, `POST /api/pets/companion-growth/seen/` clears it (idempotent). Frontend [`useCompanionGrowthToasts`](/frontend/src/hooks/useCompanionGrowthToasts.js) polls every 20s mirroring `useDropToasts`; [`CompanionGrowthToastStack`](/frontend/src/components/CompanionGrowthToastStack.jsx) renders non-evolved ticks as moss-tinted slide-in toasts and **escalates evolved events to the full `PetCeremonyModal mode="evolve"`** so the silent path gets the same celebration as the explicit feed-evolve flow. Mounted globally via [`JournalShell`](/frontend/src/components/layout/JournalShell.jsx). Pinned by [`apps/pets/tests/test_companion_growth.py`](tests/test_companion_growth.py) and [`frontend/src/components/CompanionGrowthToastStack.test.jsx`](/frontend/src/components/CompanionGrowthToastStack.test.jsx).

- **Mount sprite convention:** evolved mounts use `{species.sprite_key}-mount`; [`Mounts.jsx`](/frontend/src/pages/bestiary/party/Mounts.jsx) passes `spriteKey="${species}-mount"` + `fallbackSpriteKey={species}` to `RpgSprite`, which falls back to the base pet sprite when the mount tile isn't drawn yet. The 17 species preceding Chick had Ceph mount sprites confirmed on 2026-04-23 via `mcp__abby__list_sprites`. Chick uses the new `cute-chick` / `cute-chick-mount` presentation keys. These asset keys do not change species identity; a new mount presentation requires matching art through the existing sprite catalog or licensed portrait support, without a schema or serializer change.

- **Companions / Mounts UI split** (2026-04-26; collection controls refreshed October 2026): the old "Party" tab on `/bestiary` was lifted into two top-level Bestiary tabs — [`Companions`](/frontend/src/pages/bestiary/party/Companions.jsx) and [`Mounts`](/frontend/src/pages/bestiary/party/Mounts.jsx) — each with its own filter set (`All / Active / Hungry / Ready to evolve` for Companions; `All / Active / Out exploring / Ready to breed / On cooldown` for Mounts). Companions and Mounts pass icon, label and `×N` count descriptors to `TomeShelf` with `variant: "vessel"`; the shared control renders compact wrapping pills at every width. Empty buckets hide except `All`. Status filtering still reads `happiness_level` (Companions) and `last_bred_at` (Mounts, exposed on `UserMountSerializer`). The 7-day cooldown helper + `BREEDING_COOLDOWN_DAYS` constant live in `party.constants.js` — Hatchery imports from there too. The legacy `/stable` route + the dashboard pet vital-pip both redirect to `/bestiary?tab=companions`. Inventory action targets in `UserInventorySerializer.get_available_actions` route eggs/potions to `?tab=hatchery` and food to `?tab=companions`.

- **Bestiary codex alignment** (2026-05-16): all four Bestiary sub-tabs share the Meadow collection and progress primitives used by the Atlas / Sketchbook / SigilCodex hubs.
  - Every sub-tab (Companions, Mounts, [`BestiaryCodex`](/frontend/src/pages/bestiary/codex/BestiaryCodex.jsx), [`Hatchery`](/frontend/src/pages/bestiary/hatchery/Hatchery.jsx)) opens with an `<IncipitBand>` hero (gilt drop-cap + script kicker + meta + progress bar) instead of a bespoke `<header>`. The standalone "pets X/Y" / "mounts X/Y" / "species X/Y" `RuneBadge` chips were retired — that count is now in `IncipitBand.meta`.
  - The Codex was rebuilt to match `SigilCodex.jsx`: `IncipitBand` → `TomeShelf` wrapping collection cards (codex variant) → active chapter rendered by [`BestiaryFolio`](/frontend/src/pages/bestiary/codex/BestiaryFolio.jsx) (mirrors `CollectionFolio` — rubric numeral + `IlluminatedVersal` + `RarityStrand` + `SpeciesTile` grid).
  - [`codex.constants.js`](/frontend/src/pages/bestiary/codex/codex.constants.js) owns the chapter taxonomy. Species are bucketed by progress tier into four chapters: **Bound in Lore** (gilded — every available potion variant mounted), **Bonded** (cresting — ≥1 mount), **Hatched** (rising — pet only), **Silhouettes** (locked — undiscovered). The rarity strand per chapter aggregates each species's `available_potions` rarities (`earned` = owned mount variants at that rarity). Adding a new chapter is a one-tuple edit to `CHAPTERS` + a branch in `chapterIdForSpecies` — both pure-data, no JSX touched.
  - Active chapter persists across reloads via `localStorage` key `bestiary:codex:active-chapter` (same `useState` + try/catch shape as `SigilCodex.jsx`).
  - `SpeciesTile` + `SpeciesDetailSheet` are unchanged — only the wrapper / header gained the rubric + versal + strand decoration, so the tile-level UX (hover, lore one-liner, potion strand, locked silhouette) is preserved.
  - Pinned by [`BestiaryCodex.test.jsx`](/frontend/src/pages/bestiary/codex/BestiaryCodex.test.jsx) — tests the hero counts and selected chapter content. `Companions.test.jsx` and `Mounts.test.jsx` cover party filters through the shared tab role. `TomeShelf` follows keyboard focus and reveals offscreen controls on intentional navigation; mounting and external selection do not focus or scroll the page.

- **Generic breeding mechanics** (`PetService.breed_mounts`, 2026-04-23; asset policy enforced October 2026): combine two supported mounts the same user owns to yield an available egg + potion pair. Select one parent's species, then choose among approved compatible parental potions or a registered approved compatibility fallback. Missing compatible content fails before inventory or cooldown writes. Each parent gets a `UserMount.last_bred_at` stamp; re-breeding is blocked for `MOUNT_BREEDING_COOLDOWN_DAYS=7` days. The `CHROMATIC_UPGRADE_CHANCE=0.02` wildcard can grant Cosmic (legendary) only when both the species compatibility and asset policy approve it. Empty legacy compatibility lists do not bypass that policy. Endpoint: `POST /api/mounts/breed/ {mount_a_id, mount_b_id}`. The [`Hatchery`](/frontend/src/pages/bestiary/hatchery/Hatchery.jsx) form appears only with server-confirmed breeding availability; broad species/Cosmic scenarios in tests use explicit synthetic bindings.

- **Pet happiness** (`happiness_for_pet` in `apps/pets/services.py`, 2026-04-23; sprite dim wired 2026-05-09): buckets an unevolved pet into `happy` / `bored` / `stale` / `away` based on days since `last_fed_at` (thresholds: 3 / 7 / 14). Evolved pets are always `happy` — they're past the feeding loop. Exposed on `UserPetSerializer` as `happiness_level`. Gentle-nudge: purely visual — never penalizes coins, XP, drops, or growth. The frontend dim is real now: `RpgSprite` accepts a `dim` prop (`bored` / `stale` / `away`) that composes with the existing potion filter via the `DIM_FILTERS` map in [`frontend/src/components/rpg/RpgSprite.jsx`](/frontend/src/components/rpg/RpgSprite.jsx) (grayscale + opacity ramp; `data-dim` attribute exposed for tests). [`Companions.jsx`](/frontend/src/pages/bestiary/party/Companions.jsx) reads `pet.happiness_level`, suppresses dimming for evolved pets, and renders a soft whisper line under the pet name for `bored` ("a little bored — feed me?") and `stale` ("getting hungry — needs a snack") states. `away` is intentionally NOT in `HAPPINESS_WHISPER` (the strongest grayscale on the sprite carries that signal — adding text there would feel like a guilt-trip). Pinned by `Companions.test.jsx` ("shows a soft whisper line under bored/stale pets and dims their sprite").

- **Pet lifecycle animations** ([`frontend/src/pages/bestiary/PetCeremonyModal.jsx`](/frontend/src/pages/bestiary/PetCeremonyModal.jsx) + [`celebration/`](/frontend/src/pages/bestiary/celebration), 2026-05-09): the three "earned moment" beats — hatch, evolve, breed — share one modal with mode-specific phased sequences that read at the same intensity as `RareDropReveal`.
  - **Hatch (`mode="hatch"`)** ~2.4s: egg sprite (`big-egg`) wobbles via `animate-wobble-pulse` → cosmic-burst flash → pet sprite scale-up with potion-tinted `<PotionAura>` + `<SparkleBurst>`.
  - **Evolve (`mode="evolve"`)** ~1.5s: base pet holds with subtle aura → aura intensifies + sprite brightens via CSS filter → cosmic-burst flash with sprite swap base→mount mid-flash → mount settles with `animate-gilded-glint` sweep + gold sparkles.
  - **Breed (`mode="breed"`)** ~2.4s: two parent mount sprites slide in from L/R → cosmic-burst flash → egg + potion result reveal with sparkles. Chromatic upgrades get cosmic-tinted ring + denser/longer sparkle burst + "the stars favored this pairing" kicker.
  - **Sequence orchestration** lives in [`celebration/usePhasedSequence.js`](/frontend/src/pages/bestiary/celebration/usePhasedSequence.js) — accepts an array of phase durations, returns the current phase index 0..N. `reduced=true` jumps straight to the terminal phase. Used by the modal for all three modes.
  - **`<SparkleBurst>`** + **`<PotionAura>`** (siblings of `usePhasedSequence`) are shared decoration primitives; both are `aria-hidden` and pointer-events-none. PotionAura's color map mirrors `RpgSprite`'s `POTION_FILTERS` so a fire dragon glows red while an ice dragon glows blue — same potion vocabulary across the app.
  - **CSS contract**: two new keyframes in [`index.css`](/frontend/src/index.css) — `wobble-pulse` (0.8s, three asymmetric oscillations + small lift, transform-origin 50% 90%) and `cosmic-burst` (0.55s, radial flash that scales 0.4 → 2.4 while opacity arcs 0 → 0.9 → 0). Both are gated by the existing `@media (prefers-reduced-motion: reduce)` block, joining the cohort of celebration animations that disable on opt-out.
  - **Reduced-motion path**: every sequence collapses to its terminal "settled" frame instantly. Sparkles, flashes, aura pulses, and the egg-wobble are skipped entirely; sprites swap without animation. The `usePrefersReducedMotion` hook in the modal mirrors the pattern used by `BirthdayCelebrationModal` / `RareDropReveal` / `CelebrationModal`.
  - **Breed result API additions**: `PetService.breed_mounts` now returns `egg_item_icon`, `egg_item_sprite_key`, `potion_item_icon`, `potion_item_sprite_key`, `picked_species_slug`, `picked_potion_slug` alongside the original fields so the modal can render the result items without a follow-up inventory fetch. Original fields preserved for back-compat.
  - Pinned by [`PetCeremonyModal.test.jsx`](/frontend/src/pages/bestiary/PetCeremonyModal.test.jsx) (mode coverage + phased sequence assertions via fake timers) and [`celebration/usePhasedSequence.test.js`](/frontend/src/pages/bestiary/celebration/usePhasedSequence.test.js) / [`SparkleBurst.test.jsx`](/frontend/src/pages/bestiary/celebration/SparkleBurst.test.jsx).

- **Mount expeditions** (`apps/pets/expeditions.py` + `apps/pets/models.py::MountExpedition`, added 2026-05-10): Finch-inspired offline play loop. A user sends their mount on a 2/4/8h run via `ExpeditionLaunchSheet` on `/bestiary?tab=mounts`; the mount returns with coins + 1-3 items. Tier durations + coin/item budgets live in `TIER_CONFIG` in [`expeditions.py`](expeditions.py) (short=2h/15c/1, standard=4h/35c/2, long=8h/75c/3). **Loot is rolled at start and locked to the row's `loot` JSON field** — slow-claim users get the same payout regardless of when they tap through. Daily cap of one expedition per mount per local day enforced by both a service-level `started_at__date=today` check and a partial unique constraint on `(mount, status='active')` so a concurrent double-start surfaces a friendly error before hitting `IntegrityError`. Cross-user mount IDs return `MountExpedition not found` from the service, mapped to **404** in `StartExpeditionView` / `ClaimExpeditionView` (existence-leak prevention, matching the MCP `get_in_family` pattern). On claim:
  - `_materialize_loot` posts coins via `CoinService.award_coins(reason=CoinLedger.Reason.EXPEDITION)` — the `EXPEDITION` reason **is** on the `_BOOSTABLE_COIN_REASONS` whitelist so Lucky Coin doubles the haul. Adding a new earn-kind reason without checking this whitelist is the bug shape that bit Daily Challenge originally; pinned by `test_lucky_coin_doubles_expedition_payout` in [`tests/test_expeditions.py`](tests/test_expeditions.py).
  - Cosmetic-dupe salvage path mirrors `DropService` — owned cosmetics get auto-converted to `coin_value` instead of stacking dupes. The loot row records `salvaged_to_coins` so the claim modal can render the salvage ribbon.
  - `GameLoopService.on_task_completed(user, TriggerType.EXPEDITION_RETURNED, {drops_allowed: False, ...})` fires for streak / quest-progress credit. **`drops_allowed=False` is load-bearing**: loot was already rolled at start, the claim must not double-dip the trigger's bonus drop roll. Same precedent as `homework_created`.
  - Pre-rolled loot biases by tier rarity weights — short tier gives mostly commons, long tier opens up to rare/epic/legendary. The fallback when no `EXPEDITION_RETURNED` `DropTable` rows are seeded yet is the union of `CLOCK_OUT` + `CHORE_COMPLETE` pools (cosmetic-heavy by design), so a fresh deployment still produces sensible loot without authoring expedition-specific drops.

  **Frontend**: [`Mounts.jsx`](/frontend/src/pages/bestiary/party/Mounts.jsx) flips a mount card into the out-on-expedition state via the new `active_expedition` field on `UserMountSerializer` — sprite dims (via the existing `RpgSprite` `dim="stale"` prop), the saddle-up button disables, a countdown chip renders via `formatExpeditionRemaining(seconds_remaining)`, and the breed-cooldown chip is suppressed. Ready-to-claim mounts show a gilt "Claim loot →" button with the existing `animate-gilded-glint` flourish. Claim opens `PetCeremonyModal` in the new `mode="expedition_return"` (4th mode after `hatch` / `evolve` / `breed`) — same `usePhasedSequence` + `SparkleBurst` + reduced-motion path as the other ceremonies. **Global toast surface**: [`ExpeditionToastStack`](/frontend/src/components/ExpeditionToastStack.jsx) is mounted on `JournalShell` and polls `/api/expeditions/?ready=true` every 60s, surfacing returning mounts as soft slide-in nudges that deep-link to `/bestiary?tab=mounts`. Dismissals persist in `localStorage` under `abby:expeditions:dismissed` so a refresh doesn't re-show the same nudge — the actual claim still happens on the Mounts page (where the kid can see what they got).

  **Naming gotcha**: the new feature is named **Expeditions**, not Adventures. `frontend/src/pages/character/AdventuresEntry.jsx` already aliases "Adventures" to the Trials/Quests page, so reusing the word would create a UI collision.

  Endpoints: `POST /api/mounts/<id>/expedition/ {tier}`, `GET /api/expeditions/[?ready=true]`, `POST /api/expeditions/<id>/claim/`. New `NotificationType.EXPEDITION_RETURNED` fans the return event to the kid + parents (frontend parity in `notifications.constants.js`). New `TriggerType.EXPEDITION_RETURNED` (drop rate 0.0 since loot is pre-rolled, damage 5 — same as `habit_log`). Lorebook coverage maps for the new trigger and coin reason both alias to the `mounts` slug (rewritten to describe expeditions). Tests in [`tests/test_expeditions.py`](tests/test_expeditions.py) (15 cases) cover start/claim/cooldown/cross-user/Lucky-Coin/salvage/drops_allowed=False; frontend interaction tests in [`Mounts.test.jsx`](/frontend/src/pages/bestiary/party/Mounts.test.jsx) and [`ExpeditionToastStack.test.jsx`](/frontend/src/components/ExpeditionToastStack.test.jsx).

## Tunables (constants in `apps/pets/services.py`)
- `GROWTH_PREFERRED_FOOD = 15`, `GROWTH_NEUTRAL_FOOD = 5`, `EVOLUTION_THRESHOLD = 100` — pet growth mechanics. Food preference is FK-driven: `ItemDefinition.food_species` FK points to `PetSpecies`; `feed_pet` compares `food.food_species == pet.species` for the preferred bonus.
- `HAPPINESS_THRESHOLDS` — `happy` (≤3 days since fed), `bored` (≤7), `stale` (≤14), `away` (>14). Evolved pets always `happy`.
- `CONSUMABLE_GROWTH_DAILY_CAP = 50` — per-pet per-local-day cap on direct-grant growth from `growth_surge` and `feast_platter`. State lives on `UserPet.consumable_growth_today` + `consumable_growth_date`; the `apply_consumable_growth(amount)` model method auto-resets the counter on a new day. Tonic-doubled feeds bypass this cap because food items are themselves the limiter.
- `MOUNT_BREEDING_COOLDOWN_DAYS = 7`, `CHROMATIC_UPGRADE_CHANCE = 0.02`.

## Key entry points
- `services.py` — `PetService`, `happiness_for_pet`, growth constants.
- `expeditions.py` — `ExpeditionService`, `TIER_CONFIG`, `_materialize_loot`.
- `tests/test_companion_growth.py`, `tests/test_expeditions.py`.
