# apps/pets/

Collectible pets + timed incubation + growth/evolution + offline expeditions. Every species has the lifecycle **Egg → Baby → Middle → Grown**. An owned egg + potion starts incubation; after its server deadline an explicit hatch creates a baby. 50 saved growth reaches middle, and confirmed evolution at 100 reaches grown (the existing mount). See [companion lifecycle](../../docs/operations/companion-lifecycle.md).

## Active asset policy (October 2026)

New acquisition uses [`shared/catalog/asset-support.json`](../../shared/catalog/asset-support.json)
through `apps/rpg/catalog_support.py`. The checked-in policy supports
exact `chick` / `cute-chick`, `meshtint-wolf`, `meshtint-dragon`,
`meshtint-mushroom`, `meshtint-bee` and `meshtint-bat` with global `base`,
`fire` and `ice` potions. The other nine prepared families retain only `base`
(27 exact pairs). Bee/Bat rollout requires canonical publication/readback and
the ordinary MAIN gates. Registered eggs require exact slug, typed FK and canonical metadata
agreement. See [prepared roster adoption](../../docs/operations/companion-lifecycle.md#prepared-roster-adoption).
The read-only server `evolution_stage` is Chick below 50 persisted growth, Fledgling from 50, and Bird after confirmed evolution at 100 or for its mount. Other identities return null for this legacy artwork alias, while all species expose the generic `lifecycle_stage` and ordered species `lifecycle_stages`. See [Bird adoption](../../docs/operations/bird-evolution.md).

The owner accepted all twelve Bee/Bat Fire/Ice app appearances and authorized
their four pairs and guaranteed Hive/Cave challenges. This branch prepares
activation; canonical publication/readback must finish before MAIN merges and
deploys it. Existing egg identities stay unchanged. Bee → Bumble → Sting and
Bat → Vampire Bat → Bat Lord names apply across Base/Fire/Ice; Base Dragon
retains its names and elemental Dragon remains Dragonling → Dragon → Elder
Dragon. See [the rollout runbook](../../docs/operations/elemental-bee-bat.md).
Owning a portrait or authoring a YAML row does not enable another species,
potion variant or 3D appearance. The owner retired unused original species
rather than replacing their artwork. Default content loading attempts a
one-time, transactionally recorded retirement of those exact seventeen
identities and eggs, Shadow/Golden/Cosmic potions and known pet accessories.
Supported families and the planned global Fire/Ice ingredients remain separate
from that cleanup.

Catalog/codex and potion choices intersect this policy with
`PetSpecies.available_potions`. Hatching rejects an unavailable pair or
ingredient before consuming inventory. Stable keeps every remaining saved pet/mount,
adds read-only `catalog_available`, and counts only approved compatible pairs
in `total_possible`. React places unavailable rows in Saved collection while
retaining feeding, growth/evolution, activation and expedition controls.
Outside that exact retirement list, existing expedition history and locked
loot remain claimable under the ordinary rules; newly rolled loot is restricted
to available items. Before a listed mount is removed, retirement settles its
ACTIVE unclaimed expedition from saved Coins and surviving supported item slots
once, without rerolling, current boosts or completion rewards.

## Breeding retirement

Breeding was removed at the owner's request to keep companions focused on
collecting, hatching, care, growth and expeditions. The engine, pairing UI,
cooldown controls and MCP action are removed. Authenticated legacy
`POST /api/mounts/breed/` returns HTTP 410 with
`{"error": "Pet breeding has been removed."}` and performs no writes.
The breeding endpoint itself changes no pets, mounts, ingredients or history.
Compatibility fields are inert: `can_breed` and `breeding_available` are always
false, and `breeding_cooldown_seconds` is zero. They grant no capability.

## Models

The Fire/Ice policy enables exact Chick/Wolf/Dragon/Mushroom/Bee/Bat compatibility
and twelve guaranteed challenges; the other nine prepared families remain Base
only. Bee/Bat activation uses the ordinary MAIN gates after canonical
publication/readback. Expedition starts now share one allowance per
account/species across potion appearances, including any unclaimed trip.
Accepted trips retain their frozen rewards. See
[Fire/Ice delivery state](../../docs/operations/fire-ice-companions.md).

- `PetIncubation` saves one accepted ingredient pair, request UUID, frozen display identities and start/ready timestamps. One unfinished row per account includes ready eggs awaiting explicit hatch. Completed rows retain their request receipt and hatch marker; deleting a saved pet cannot make that receipt award it again. User deletion cascades the row; ingredient deletion clears its optional FK while retaining its snapshot. Species/potion deletion is protected so accepted identities remain fulfillable; ordinary catalog retirement never prevents claim. The owner's explicit unused-content retirement returns matching consumed supported ingredients from an unfinished accepted pair before deleting the obsolete receipt and identity; completed hatches do not return ingredients.
- `PetSpecies.rarity` is its acquisition tier, shared with the canonical egg.
  Owned pet/mount responses expose the higher of species rarity and a saved
  potion rarity, preserving legacy variants. Growth stages never change rarity.
- `PetSpecies` (15 prepared families with 27 approved species/potion pairs: Base for every family plus Fire/Ice for Chick, Wolf, Dragon, Mushroom, Bee and Bat), `PotionType` (Base, Fire and Ice), `PetSpecies.available_potions` M2M declares compatible combinations.
- `UserPet` (growth 0-100, `last_fed_at`, `evolved_to_mount`, `consumable_growth_today` + `consumable_growth_date`), `UserMount` (`last_bred_at`).
- `MountExpedition` (offline adventure rows; `status`, `tier`, `started_at`, `ready_at`, `loot` JSON).

## Services
- `PetService` — `start_incubation`, `current_incubation`, `hatch_incubation`, `feed_pet`, `evolve`, `set_active_pet`, `set_active_mount`, `auto_grow_companions`, `happiness_for_pet`, `get_stable(user)` (returns dict with pets, mounts, totals for StableView).
- `ExpeditionService` (`apps/pets/expeditions.py`) — `start`, `claim`, `list_for_user`. `TIER_CONFIG` (short/standard/long). Exceptions: `ExpeditionError`, `ExpeditionNotFound`.

New expeditions have 3 / 7 / 15 base Coins for 2 / 4 / 8 hours, with existing
variation, item slots and claim-time Lucky Coin behavior. Newly rolled pouch
items use the reduced versioned definitions before freezing loot. Existing
trips keep their saved Coins and exact item IDs; claim never applies the new
random-award resolver. See [Coin pacing](../../docs/operations/coin-economy.md).

### Growth transactions

Incubation starts acquire the achievements user gate before inventory writes,
validate the current pair and ownership, and consume exactly one egg + potion.
They create no pet, growth, badge, XP, Coins or Chronicle hatch. Replaying the
same request UUID and pair returns the saved row, including after completion;
changing the pair for that UUID conflicts. Another unfinished egg conflicts.
`PET_INCUBATION_DURATION_SECONDS` defaults to 86400 (24 hours) and is frozen into
`ready_at`. A later setting change affects new eggs only; accepted eggs retain
their original deadlines, including eggs accepted under an earlier duration.
Reads report server time, rounded-up remaining seconds and readiness without
writing. Only an explicit ready hatch creates ownership and its existing rewards,
under the same user-first lock and a lock on the incubation row itself. Catalog
availability/compatibility changes after acceptance do not revoke that paid pair.
Claim retries return the original pet with `freshly_hatched: false`; a payout
failure rolls back the claim while retaining its already reserved ingredients.
No worker, browser timer, GET or instant service can hatch an egg early.
`tests/test_incubation.py` and the PostgreSQL concurrency tests cover these rules.

Hatching and confirmed evolution evaluate the existing `pet` and `badges`
achievement scopes immediately, in the same transaction as ownership and item
reservation. Starting and hatching acquire the achievements user gate before
inventory or incubation locks. Food, Growth Surge, Feast and passive growth all reach evolution's
badge evaluation through `PetService._save_growth`; intermediate growth grants
no new badge rule or reward. Existing badge criteria, XP and Coin values stay
authoritative. A failed badge payout rolls back the pet/mount and payout together;
food consumption rolls back, while a previously accepted egg remains reserved
for its claim retry.
Only newly earned badges create self-scoped `badge_earned` notifications linking
to Badges. Their rows use a best-effort savepoint, and external push waits for
the ownership transaction to commit; a notification failure retains progression
and its authoritative badge payout. These hooks never run the broader game loop.
`tests/test_badge_milestones.py` covers milestone timing, account isolation,
retries and rollback through these care paths.

Food base growth has rarity floors 5/8/10/12/15 from Common through Legendary.
An integer authored `metadata.growth` in 1..30 can raise that floor; malformed,
boolean or out-of-range legacy values use the floor. Preferred food adds 10
before Growth/Morale Tonic doubles the total and spends one charge. Common
neutral/preferred feeds therefore retain 5/15 growth. Inventory and the food
chooser display the same server-owned `effect_summary` used by feeding.

Food, direct consumables and passive Companion growth acquire the achievements
user `NO KEY UPDATE` gate before profile/pet/inventory writes. Growth Surge
locks its selected pet, as feeding and Feast already do. A concurrent feed and
surge preserve both consumed items' growth; a competing evolution cannot consume
food for an already evolved pet. Growth/Morale Tonic charges double preferred
and neutral feeds and decrement once with the successful food transaction;
failure preserves the charge and food. Boosted food does not use the direct
consumable daily cap.

Pet activation and expedition claims take the same user gate before touching
pet, receipt or inventory rows. Claims lock only the expedition row with
`select_for_update(of=("self",))`; joined mount, species and potion rows stay
unlocked so another family's hatching/evolution can use the shared catalog.
`test_care_lock_order.py` reproduces the former claim/evolution and
activation/Feast deadlocks on PostgreSQL and checks preserved rewards and growth.

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
available only with no active/unclaimed expedition on any owned appearance of
its species and no species expedition started that Django local day. Claimed
and expired runs still use today's allowance.
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
- `GET /api/pets/incubations/` — self-scoped unfinished incubation or null, configured duration and server time.
- `POST /api/pets/incubations/ {egg_item_id,potion_item_id,request_id}` — start (201) or replay the same request (200). Invalid pairs return 400; conflicting unfinished eggs or UUID reuse return 409.
- `POST /api/pets/incubations/<id>/hatch/` — explicit ready hatch (201) or completed retry (200), with `pet` and `freshly_hatched`. Early hatch returns 409; foreign/missing IDs return 404. All envelopes carry `server_now` and frozen incubation display fields. Remaining seconds and readiness share that server snapshot.
- Authenticated legacy `POST /api/pets/hatch/` returns 410 with `{"error":"Instant hatching has been removed. Start an egg incubation in the Hatchery."}` and performs no writes. There is no public instant-hatch service.
- `POST /api/mounts/<id>/expedition/ {tier}` — start an expedition.
- `GET /api/expeditions/[?ready=true]` — list user's expeditions.
- `POST /api/expeditions/<id>/claim/` — claim returned loot.
- `GET /api/pets/companion-growth/recent/` + `POST /api/pets/companion-growth/seen/` — companion auto-grow queue.

## Gotchas

- **Potion compatibility** (October 2026): hatching checks a species's nonempty `available_potions` before consuming ingredients. The loader populates omitted lists with all current potion types; an empty legacy relation means unrestricted authored compatibility, still intersected with the active asset policy for new hatching. Chick accepts Base, Fire and Ice and prefers Birdseed food. Its licensed Chick / Fledgling / Bird appearances describe one species with server-derived growth stages, not three ownership identities. Fledgling at 50 adds no reward or mount; the existing 100-growth evolution remains authoritative. Supported companion ownership remains intact on repeated content loads; the exact unused legacy identities are retired by the default loader's one-time transition. [`test_cute_chick_catalog.py`](tests/test_cute_chick_catalog.py) covers the additive catalog, preservation and lifecycle rules.

- **Pets & mounts**: Lifecycle is **Egg + Potion → Baby → Middle → Grown → Expeditions**. `PetService.start_incubation` consumes one egg item and one potion item from `UserInventory`, reads `egg.pet_species` and `potion.potion_type` FKs (registered production eggs require canonical metadata agreement; only retained nonregistered legacy rows may use metadata fallback), enforces one pet per `(user, species, potion)` combo, and reserves the accepted pair until its saved deadline. `PetService.hatch_incubation` explicitly creates a `UserPet` with `growth_points=0` when ready. `PetSpecies.available_potions` M2M declares which species × potion combos are valid (defaults to all potions when unspecified in a content pack). `PetService.feed_pet` consumes a food item, stamps `UserPet.last_fed_at`, and adds the food rarity/authored base plus 10 if `food.food_species == pet.species` (preferred, FK-driven); tonic doubles the total. **Consumable growth daily cap** (2026-04-23): direct-grant consumables `growth_surge` (+30 to active pet) and `feast_platter` (+10 to every unevolved pet) route through `UserPet.apply_consumable_growth(amount)` which enforces `CONSUMABLE_GROWTH_DAILY_CAP=50` per pet per local day. `growth_surge` returns `{growth_requested, growth_added, growth_capped, ...}` so callers can see when the cap clamped the boost; `feast_platter` returns a per-pet array. Tonic-doubled feeds are NOT capped — they require food items to exist, which is a natural limiter. Without the cap, hoarded consumables could fully evolve a pet (0 → 100) in a single sitting; the design intent is real-world weeks of bonding. Pinned by `ConsumableGrowthDailyCapTests` in [`apps/rpg/tests/test_new_consumable_effects.py`](/apps/rpg/tests/test_new_consumable_effects.py). At `growth_points >= 100`, the pet auto-evolves: `UserPet.evolved_to_mount=True` and a matching `UserMount` row is created (the original pet is retained in the stable). Only one `UserPet` and one `UserMount` can be `is_active=True` per user at a time — `set_active_pet`/`set_active_mount` deactivate any current one in the same transaction. Dashboard displays the active pet with a growth bar.

- **Companion species** (`slug=companion`) is a slow-burn pet that grows passively via `PetService.auto_grow_companions` on daily check-in; [`Companions.jsx`](/frontend/src/pages/bestiary/party/Companions.jsx) surfaces a "grows on its own — every daily check-in adds a little" line on the pet card so the mechanic isn't invisible. **Companion auto-grow surface** (2026-05-09): `auto_grow_companions` returns an `events` list (one entry per pet with `growth_added`, `new_growth`, `evolved`, `mount_id`, plus species/potion display metadata) and persists the same events to `CharacterProfile.pending_companion_growth` (JSONField — accumulates across un-seen ticks so a returning user catches up on every day they missed). Two endpoints expose the queue: `GET /api/pets/companion-growth/recent/` returns it, `POST /api/pets/companion-growth/seen/` clears it (idempotent). Frontend [`useCompanionGrowthToasts`](/frontend/src/hooks/useCompanionGrowthToasts.js) polls every 20s mirroring `useDropToasts`; [`CompanionGrowthToastStack`](/frontend/src/components/CompanionGrowthToastStack.jsx) renders non-evolved ticks as moss-tinted slide-in toasts and **escalates evolved events to the full `PetCeremonyModal mode="evolve"`** so the silent path gets the same celebration as the explicit feed-evolve flow. Mounted globally via [`JournalShell`](/frontend/src/components/layout/JournalShell.jsx). Pinned by [`apps/pets/tests/test_companion_growth.py`](tests/test_companion_growth.py) and [`frontend/src/components/CompanionGrowthToastStack.test.jsx`](/frontend/src/components/CompanionGrowthToastStack.test.jsx).

- **Mount sprite convention:** evolved mounts use `{species.sprite_key}-mount`; [`Mounts.jsx`](/frontend/src/pages/bestiary/party/Mounts.jsx) passes `spriteKey="${species}-mount"` + `fallbackSpriteKey={species}` to `RpgSprite`, which falls back to the base pet sprite when the mount tile isn't drawn yet. The 17 species preceding Chick had Ceph mount sprites confirmed on 2026-04-23 via `mcp__abby__list_sprites`. Chick uses the new `cute-chick` / `cute-chick-mount` presentation keys. These asset keys do not change species identity; a new mount presentation requires matching art through the existing sprite catalog or licensed portrait support, without a schema or serializer change.

- **Pets UI:** Companions keeps All / Active / Baby / Middle / Hungry / Almost grown filters. Grown pets keeps All / Active / Out exploring. Both use `TomeShelf` and preserve saved collections. Hatchery starts existing egg + potion incubations, shows the server wait, and explicitly hatches ready eggs. Confirmed mutations refresh all visited Pets tabs without remounting filters or forms. The `/stable` redirect and inventory action routes remain unchanged.

- **Bestiary codex alignment** (2026-05-16): all four Bestiary sub-tabs share the Meadow collection and progress primitives used by the Atlas / Sketchbook / SigilCodex hubs.
  - Every sub-tab (Companions, Mounts, [`BestiaryCodex`](/frontend/src/pages/bestiary/codex/BestiaryCodex.jsx), [`Hatchery`](/frontend/src/pages/bestiary/hatchery/Hatchery.jsx)) opens with an `<IncipitBand>` hero (gilt drop-cap + script kicker + meta + progress bar) instead of a bespoke `<header>`. The standalone "pets X/Y" / "mounts X/Y" / "species X/Y" `RuneBadge` chips were retired — that count is now in `IncipitBand.meta`.
  - The Codex was rebuilt to match `SigilCodex.jsx`: `IncipitBand` → `TomeShelf` wrapping collection cards (codex variant) → active chapter rendered by [`BestiaryFolio`](/frontend/src/pages/bestiary/codex/BestiaryFolio.jsx) (mirrors `CollectionFolio` — rubric numeral + `IlluminatedVersal` + `RarityStrand` + `SpeciesTile` grid).
  - [`codex.constants.js`](/frontend/src/pages/bestiary/codex/codex.constants.js) owns the chapter taxonomy. Species are bucketed by progress tier into four chapters: **Bound in Lore** (gilded — every available potion variant mounted), **Bonded** (cresting — ≥1 mount), **Hatched** (rising — pet only), **Silhouettes** (locked — undiscovered). The rarity strand per chapter aggregates each species's `available_potions` rarities (`earned` = owned mount variants at that rarity). Adding a new chapter is a one-tuple edit to `CHAPTERS` + a branch in `chapterIdForSpecies` — both pure-data, no JSX touched.
  - Active chapter persists across reloads via `localStorage` key `bestiary:codex:active-chapter` (same `useState` + try/catch shape as `SigilCodex.jsx`).
  - `SpeciesTile` + `SpeciesDetailSheet` are unchanged — only the wrapper / header gained the rubric + versal + strand decoration, so the tile-level UX (hover, lore one-liner, potion strand, locked silhouette) is preserved.
  - Pinned by [`BestiaryCodex.test.jsx`](/frontend/src/pages/bestiary/codex/BestiaryCodex.test.jsx) — tests the hero counts and selected chapter content. `Companions.test.jsx` and `Mounts.test.jsx` cover party filters through the shared tab role. `TomeShelf` follows keyboard focus and reveals offscreen controls on intentional navigation; mounting and external selection do not focus or scroll the page.



- **Pet happiness** (`happiness_for_pet` in `apps/pets/services.py`, 2026-04-23; sprite dim wired 2026-05-09): buckets an unevolved pet into `happy` / `bored` / `stale` / `away` based on days since `last_fed_at` (thresholds: 3 / 7 / 14). Evolved pets are always `happy` — they're past the feeding loop. Exposed on `UserPetSerializer` as `happiness_level`. Gentle-nudge: purely visual — never penalizes coins, XP, drops, or growth. The frontend dim is real now: `RpgSprite` accepts a `dim` prop (`bored` / `stale` / `away`) that composes with the existing potion filter via the `DIM_FILTERS` map in [`frontend/src/components/rpg/RpgSprite.jsx`](/frontend/src/components/rpg/RpgSprite.jsx) (grayscale + opacity ramp; `data-dim` attribute exposed for tests). [`Companions.jsx`](/frontend/src/pages/bestiary/party/Companions.jsx) reads `pet.happiness_level`, suppresses dimming for evolved pets, and renders a soft whisper line under the pet name for `bored` ("a little bored — feed me?") and `stale` ("getting hungry — needs a snack") states. `away` is intentionally NOT in `HAPPINESS_WHISPER` (the strongest grayscale on the sprite carries that signal — adding text there would feel like a guilt-trip). Pinned by `Companions.test.jsx` ("shows a soft whisper line under bored/stale pets and dims their sprite").

- **Pet lifecycle animations** ([`frontend/src/pages/bestiary/PetCeremonyModal.jsx`](/frontend/src/pages/bestiary/PetCeremonyModal.jsx) + [`celebration/`](/frontend/src/pages/bestiary/celebration), 2026-05-09): the earned moments — hatch, evolve and expedition return — share one modal with mode-specific phased sequences that read at the same intensity as `RareDropReveal`.
  - **Hatch (`mode="hatch"`)** ~2.4s: egg sprite (`big-egg`) wobbles via `animate-wobble-pulse` → cosmic-burst flash → pet sprite scale-up with potion-tinted `<PotionAura>` + `<SparkleBurst>`.
  - **Evolve (`mode="evolve"`)** ~1.5s: base pet holds with subtle aura → aura intensifies + sprite brightens via CSS filter → cosmic-burst flash with sprite swap base→mount mid-flash → mount settles with `animate-gilded-glint` sweep + gold sparkles.
  - **Sequence orchestration** lives in [`celebration/usePhasedSequence.js`](/frontend/src/pages/bestiary/celebration/usePhasedSequence.js) — accepts an array of phase durations, returns the current phase index 0..N. `reduced=true` jumps straight to the terminal phase. Used by the modal for all three modes.
  - **`<SparkleBurst>`** + **`<PotionAura>`** (siblings of `usePhasedSequence`) are shared decoration primitives; both are `aria-hidden` and pointer-events-none. PotionAura's color map mirrors `RpgSprite`'s `POTION_FILTERS` so a fire dragon glows red while an ice dragon glows blue — same potion vocabulary across the app.
  - **CSS contract**: two new keyframes in [`index.css`](/frontend/src/index.css) — `wobble-pulse` (0.8s, three asymmetric oscillations + small lift, transform-origin 50% 90%) and `cosmic-burst` (0.55s, radial flash that scales 0.4 → 2.4 while opacity arcs 0 → 0.9 → 0). Both are gated by the existing `@media (prefers-reduced-motion: reduce)` block, joining the cohort of celebration animations that disable on opt-out.
  - **Reduced-motion path**: every sequence collapses to its terminal "settled" frame instantly. Sparkles, flashes, aura pulses, and the egg-wobble are skipped entirely; sprites swap without animation. The `usePrefersReducedMotion` hook in the modal mirrors the pattern used by `BirthdayCelebrationModal` / `RareDropReveal` / `CelebrationModal`.
  - Pinned by [`PetCeremonyModal.test.jsx`](/frontend/src/pages/bestiary/PetCeremonyModal.test.jsx) (mode coverage + phased sequence assertions via fake timers) and [`celebration/usePhasedSequence.test.js`](/frontend/src/pages/bestiary/celebration/usePhasedSequence.test.js) / [`SparkleBurst.test.jsx`](/frontend/src/pages/bestiary/celebration/SparkleBurst.test.jsx).

- **Mount expeditions** (`apps/pets/expeditions.py` + `apps/pets/models.py::MountExpedition`, added 2026-05-10): Finch-inspired offline play loop. A user sends their mount on a 2/4/8h run via `ExpeditionLaunchSheet` on `/bestiary?tab=mounts`; the mount returns with coins + 1-3 items. Tier durations + coin/item budgets live in `TIER_CONFIG` in [`expeditions.py`](expeditions.py) (short=2h/15c/1, standard=4h/35c/2, long=8h/75c/3). **Loot is rolled at start and locked to the row's `loot` JSON field** — slow-claim users get the same payout regardless of when they tap through. Daily cap of one expedition per mount per local day enforced by both a service-level `started_at__date=today` check and a partial unique constraint on `(mount, status='active')` so a concurrent double-start surfaces a friendly error before hitting `IntegrityError`. Cross-user mount IDs return `MountExpedition not found` from the service, mapped to **404** in `StartExpeditionView` / `ClaimExpeditionView` (existence-leak prevention, matching the MCP `get_in_family` pattern). On claim:
  - `_materialize_loot` posts coins via `CoinService.award_coins(reason=CoinLedger.Reason.EXPEDITION)` — the `EXPEDITION` reason **is** on the `_BOOSTABLE_COIN_REASONS` whitelist so Lucky Coin doubles the haul. Adding a new earn-kind reason without checking this whitelist is the bug shape that bit Daily Challenge originally; pinned by `test_lucky_coin_doubles_expedition_payout` in [`tests/test_expeditions.py`](tests/test_expeditions.py).
  - New expeditions freeze cosmetic duplicate salvage at at most 10 Coins per slot when launched; older loot without that snapshot retains its established full-value claim path. The loot row records `salvaged_to_coins` so the claim modal can render the salvage ribbon.
  - `GameLoopService.on_task_completed(user, TriggerType.EXPEDITION_RETURNED, {drops_allowed: False, ...})` fires for streak / quest-progress credit. **`drops_allowed=False` is load-bearing**: loot was already rolled at start, the claim must not double-dip the trigger's bonus drop roll. Same precedent as `homework_created`.
  - New loot uses fixed conditional tier budgets: short 70/25/5 Common/Uncommon/Rare; standard 50/35/13/2 through Epic; long 35/35/22/7/1 through Legendary. Unlisted tiers are excluded and absent tiers renormalize. Authored weights choose within a tier, so catalog size cannot dilute another tier. Unowned cosmetics precede duplicate salvage within their tier/category. The fallback is the union of positive `CLOCK_OUT` + `CHORE_COMPLETE` entries; current seed content in that fallback is mostly food/pouches/eggs, not cosmetics. Saved pre-rolled loot remains unchanged.

  **Frontend**: [`Mounts.jsx`](/frontend/src/pages/bestiary/party/Mounts.jsx) flips a mount card into the out-on-expedition state via the new `active_expedition` field on `UserMountSerializer` — sprite dims (via the existing `RpgSprite` `dim="stale"` prop), the saddle-up button disables, a countdown chip renders via `formatExpeditionRemaining(seconds_remaining)`. Ready-to-claim mounts show a gilt "Claim loot →" button with the existing `animate-gilded-glint` flourish. Claim opens `PetCeremonyModal` in the new `mode="expedition_return"` (alongside `hatch` and `evolve`) — same `usePhasedSequence` + `SparkleBurst` + reduced-motion path as the other ceremonies. **Global toast surface**: [`ExpeditionToastStack`](/frontend/src/components/ExpeditionToastStack.jsx) is mounted on `JournalShell` and polls `/api/expeditions/?ready=true` every 60s, surfacing returning mounts as soft slide-in nudges that deep-link to `/bestiary?tab=mounts`. Dismissals persist in `localStorage` under `abby:expeditions:dismissed` so a refresh doesn't re-show the same nudge — the actual claim still happens on the Mounts page (where the kid can see what they got).

  **Naming gotcha**: the new feature is named **Expeditions**, not Adventures. `frontend/src/pages/character/AdventuresEntry.jsx` already aliases "Adventures" to the Trials/Quests page, so reusing the word would create a UI collision.

  Endpoints: `POST /api/mounts/<id>/expedition/ {tier}`, `GET /api/expeditions/[?ready=true]`, `POST /api/expeditions/<id>/claim/`. New `NotificationType.EXPEDITION_RETURNED` fans the return event to the kid + parents (frontend parity in `notifications.constants.js`). New `TriggerType.EXPEDITION_RETURNED` (drop rate 0.0 since loot is pre-rolled, damage 5 — same as `habit_log`). Lorebook coverage maps for the new trigger and coin reason both alias to the `mounts` slug (rewritten to describe expeditions). Tests in [`tests/test_expeditions.py`](tests/test_expeditions.py) (15 cases) cover start/claim/cooldown/cross-user/Lucky-Coin/salvage/drops_allowed=False; frontend interaction tests in [`Mounts.test.jsx`](/frontend/src/pages/bestiary/party/Mounts.test.jsx) and [`ExpeditionToastStack.test.jsx`](/frontend/src/components/ExpeditionToastStack.test.jsx).

## Tunables (constants in `apps/pets/services.py`)
- `GROWTH_PREFERRED_FOOD = 15`, `GROWTH_NEUTRAL_FOOD = 5` retain the common-food baseline; feeding uses `food_base_growth` plus `PREFERRED_FOOD_BONUS = 10`. `EVOLUTION_THRESHOLD = 100` remains unchanged. Food preference is FK-driven: `ItemDefinition.food_species` FK points to `PetSpecies`; `feed_pet` compares `food.food_species == pet.species` for the preferred bonus.
- `HAPPINESS_THRESHOLDS` — `happy` (≤3 days since fed), `bored` (≤7), `stale` (≤14), `away` (>14). Evolved pets always `happy`.
- `CONSUMABLE_GROWTH_DAILY_CAP = 50` — per-pet per-local-day cap on direct-grant growth from `growth_surge` and `feast_platter`. State lives on `UserPet.consumable_growth_today` + `consumable_growth_date`; the `apply_consumable_growth(amount)` model method auto-resets the counter on a new day. Tonic-doubled feeds bypass this cap because food items are themselves the limiter.

## Key entry points
- `services.py` — `PetService`, `happiness_for_pet`, growth constants.
- `expeditions.py` — `ExpeditionService`, `TIER_CONFIG`, `_materialize_loot`.
- `tests/test_companion_growth.py`, `tests/test_expeditions.py`.

Prepared roster adoption supplies the fifteen current families.
`reconcile_companion_catalog --dry-run --json` reports stale configuration; its
idempotent apply removes unsupported egg/potion drop rows and deactivates digital
offers without deleting definitions or promised rewards. `loadrpgcontent` runs
this reconciliation transactionally. New eggs share the existing category weight
in drops, expeditions and mystery boxes. Dummy is future training art only and
has no companion or acquisition binding. The separate
`retire_unused_rpg_content --dry-run --json` command reports the owner's exact
unused-content removal and resource settlement. Default `loadrpgcontent` attempts
that transition once before bundled upserts, recording its completion only with
the successful cleanup transaction. It prunes exact obsolete JSON slots and
removes their ownership/receipts after returning supported ingredients from
unfinished incubations and settling unclaimed saved expedition resources. Accounts and
existing ledger entries remain; refunds and settlement can increase balances.
Supported families, Base/Fire/Ice and unrelated/custom identities remain. Changed
identity, protected-reference or resource-validation conflicts roll back all
retirement writes and warn while startup continues without a success marker;
the explicit manual command remains strict. Dry runs and later bundled-load
failures roll back resources, deletion and the completion marker together.

## Prospective Coin limits

New starts share a two-expedition daily allowance per child across every species and potion appearance. The family-local interval counts all saved launch receipts, including claimed, expired and older launches; claiming or retrying cannot reset the allowance. Existing active trips remain claimable in full. Per-species limits still apply inside this shared allowance. New trips use 3/7/15 base Coins and freeze smaller random pouch identities and each cosmetic slot's `salvage_coins_snapshot` before acceptance. Claim-time Lucky Coin eligibility remains unchanged; saved items and old loot are never rerolled or capped at claim.
