# apps/rpg/

Habitica-inspired RPG layer: character profiles, streaks, drops, consumables (14 effects), cosmetics, the central `GameLoopService` orchestrator, and the runtime-authored sprite catalog. **Qualifying activity enters through `GameLoopService.on_task_completed(user, trigger_type, context)`.** Badge, quest and Perfect Day completion loot uses the separate drop-only accomplishment hook described below.

## Supported-art catalog (October 2026)

[`shared/catalog/asset-support.json`](../../shared/catalog/asset-support.json)
is the positive production registry; `catalog_support.py` provides the shared
selectors used by pets, inventory, drops, expeditions, quest item rewards,
digital shop offers and development grants. Chick and fourteen prepared
namespaced families accept Base only. Egg/potion typed FKs take precedence over
legacy metadata, whose names/slugs must resolve to an approved catalog row.
Artwork filenames and generic icons do not establish supported acquisition.
The shipped roster contains fifteen families. The owner's unused-content
retirement removes the seventeen original species/eggs, Shadow/Golden/Cosmic
potions and known unsupported pet accessories. Base, Fire and Ice definitions
remain; Fire/Ice acquisition still requires their separately approved art policy.

`ItemDefinitionSerializer.catalog_available` distinguishes offers from saved
ownership. New item/cosmetic catalogs omit unavailable rows; owned inventory
and cosmetic reads retain them, without blocked hatch/equip actions. Frames,
Titles and valid Covers are implemented DOM cosmetics. Pet accessories have
no supported fitted art: new grants and equip are rejected. Cleanup clears
equipped references to the explicitly retired items. Avatar appearance choices
remain separate saved presentation preferences.

Drop and mystery/lucky-dip pools filter before selection. An empty eligible
pool cannot grant an unsupported item; random consumable use fails without
consuming the box/dip when no eligible reward exists. Quest completion skips
unsupported item grants without substituting Coins, while keeping authored
XP/coin rewards. Outside the exact unused-content retirement list, previously
committed rewards, ownership and locked expedition loot keep their existing
reconciliation/claim paths.
`force_drop` and hatch-ingredient helpers use the same policy.

The production registry is immutable by default. A scoped
`@override_settings(RPG_ASSET_SUPPORT_POLICY=...)` supplies explicit synthetic
bindings for generic domain tests; it is not an acquisition bypass in the app.
Coverage lives in `tests/test_catalog_support.py`,
`tests/test_asset_supported_acquisition.py` and `tests/test_catalog_consumers.py`;
the asset preparation/license boundary is
[`content/rpg/react-three-fiber-assets.md`](../../content/rpg/react-three-fiber-assets.md).

## Models
- `CharacterProfile` (level, streaks, cosmetic slots, `streak_freeze_expires_at`, boost timers, `active_trophy_badge`). Level caches the tier of total saved skill XP using `XP_THRESHOLDS` (0..6), refreshed by direct and badge XP writes. Character responses include read-only `total_xp`, `xp_in_level` and `xp_needed_for_level` (band width; both band fields are zero at level 6). Migration 0028 normalizes legacy cached levels without granting XP or rewards; appearance-only updates preserve saved levels.
- `PerfectDayReceipt` — unique `(user, day)` award guard, committed atomically with the counter, 15 coins, activity and notification; `historical` identifies receipts reconstructed from typed legacy Perfect Day events without altering rewards.
- `ItemDefinition` (10 item types incl. consumable, 5 rarities). Typed cross-entity FKs: `pet_species`, `potion_type`, `food_species`. `metadata` JSONField for free-form per-type fields.
- `ItemDefinition.display_name` projects current color-theme labels from `shared/catalog/theme-presentation.json`, including seasonal aliases. API item/character/drop/reward names and new reward snapshots use this presentation value; stored catalog names, ownership, palette keys and exact artwork bindings stay intact. Unknown themes and other item names retain their saved labels. Historical frozen receipts are not rewritten. The existing storybook sync command copies the same label registry into React.
- `UserInventory`, `DropTable`, `DropLog`

## Rarity, effects and collection paths

`rarity.py` separates successful-draw tier budgets from authored within-tier
item weights. Ordinary drops use Common/Uncommon/Rare/Epic/Legendary weights
60/25/10/4/1; milestone, project, badge, quest, Perfect Day and savings-goal
completions use 40/30/20/8/2. Missing eligible tiers renormalize over those
remaining; these are conditional draw budgets, not per-activity drop rates.
Streak/Drop Charm only affect whether a drop occurs. Macro rarity maps now
assign omitted tiers zero weight, including previously materialized rows.
Mystery Box uses 70/30 Common/Uncommon; Lucky Dip uses 60/30/10
Uncommon/Rare/Epic (an explicitly allowed Legendary pool has weight 1).
Supported egg category normalization happens before tier balancing.

Within each tier, unowned cosmetics receive the tier's cosmetic weight before
duplicates. Fully owned tiers retain salvage; new `DropLog.salvage_coins`
records the exact payout, while old null values remain unknown. Expedition
pre-rolls also avoid repeating a newly selected cosmetic within one trip.
Saved loot/receipts are never rerolled or backfilled from current prices.

`item_effects.py` supplies authoritative food growth and human-readable item
effects. `acquisition.py` batches per-request hints: accepted personal challenge
promises take precedence over later definition edits, new public system
challenges honor badge/completion gates, shop names stay family-scoped, and
drop paths honor level/positive-weight eligibility. Reading hints awards
nothing. No source is advertised for an unavailable item.

Each newly earned badge, completed quest/automatic goal (per recipient), and
Perfect Day receives one accomplishment drop through
`DropService.award_accomplishment`. The draw shares the existing earned badge,
quest payout or daily receipt transaction and account lock: retries and
concurrent completions cannot duplicate it, and a drop failure rolls the award
back for retry. Previously completed accomplishments are not backfilled.
Declared quest items remain separate from this extra loot. The helper never
replays streaks, check-in Coins, daily bonuses or challenge progress. Supported
catalog, level and salvage rules still apply; an empty eligible pool never
substitutes unsupported loot. Perfect Day filters out Common items before
selection, retaining its Uncommon-or-better reward. `drop_tier_weights` is shared
with the Lab. Drop notifications are best effort, with push deferred to commit.

Species acquisition rarity is authored with `egg_rarity`; supported families
span 5 Common, 5 Uncommon, 3 Rare, 1 Epic and 1 Legendary. Five nonrepeatable
Companion Trails guarantee supported Rare+ eggs plus a Base potion through
the existing factual Challenge engine, with no extra Coins or XP.
- `SpriteAsset` (runtime-authored sprite catalog — slug + ImageField + animation metadata + authoring inputs `prompt / original_intent / motion / style_hint / tile_size / reference_image_url` — retained as historical metadata; no in-app generation or reroll).

## Services (`apps/rpg/services.py`)
- `StreakService`, `DropService`, `CosmeticService`, `ConsumableService`, `GameLoopService` (central orchestrator).
- `InventoryItemService` — `open_coin_pouch(user, item)` converts a `coin_pouch` item to coins via `CoinService.award_coins`. Endpoint: `POST /api/inventory/<item_id>/open/`.
- `sprite_authoring.py`: `register_sprite`, `register_sprite_batch`, `delete_sprite`, `get_catalog` — write to the abby-sprites Ceph bucket.
- `storage.py::sprite_storage()` — lazy-helper for the dedicated sprites STORAGES key.
- `constants.py`: shared `TriggerType` TextChoices.

Celery tasks: `evaluate_perfect_day_task` — runs at 23:55 in the configured scheduler timezone, retains the configured local worker/streak date (currently America/Phoenix), and awards `perfect_days_count += 1`, 15 bonus coins and an Uncommon-or-better accomplishment drop once per child/day when the child was active and every eligible scheduled daily chore is approved. Pending/rejected/withdrawn submissions cannot qualify. The "at least one scheduled" guard prevents zero-chore days from auto-qualifying; a unique receipt and user/profile row locks protect duplicate/concurrent delivery, with all award state rolling back together on failure. `streak_at_risk_warning_task` — runs at 19:00 local, sends a `streak_at_risk` notification (child only, no parent fan-out, max one per local day) to any kid with `login_streak >= 3` (`STREAK_AT_RISK_MIN`) whose `last_active_date` is before today; kids with an armed `streak_freeze_expires_at` covering today are skipped. Companion in-page signal: `StreakAtRiskBanner` on `ChildDashboard` renders the same condition from the dashboard payload's `rpg` block and self-clears once any activity advances `last_active_date`.

Perfect Day reads new daily chore approvals using the frozen
`timing_snapshot.submitted_at` converted to Django's default worker timezone.
The household-local `completed_date` remains the child's schedule identity;
`created_at`, delayed approval and later family timezone edits do not move a
submission between worker days. Versioned evidence must describe a consistent
daily household period and an aware, valid timestamp/zone; malformed, unsupported
or weekly/one-time snapshots cannot fall back to a period date. Legacy null
snapshots retain their original `completed_date` worker-day interpretation,
without backfilling dates. Eligibility still uses active, published, assigned or
shared daily chores in the child's family and the existing worker-week schedule.
Two batched chore/evidence reads replace availability's per-chore status reads;
the candidate window covers at most five approved periods per eligible chore.
Receipts continue to prevent duplicate delivery or cross-day reuse.

Drop grants lock an existing inventory stack through the atomic grant, matching
the row locks used by consumables, feeding, hatching and pouch opening. If the
last unit is consumed first, the drop waits and recreates the stack; if the
drop reads first, consumption waits and preserves the newly granted unit.
`tests/test_drop_inventory_concurrency.py` checks both orders on PostgreSQL,
including the habit response, saved drop receipt, effect and remaining item.

`inventory.py::grant_item` coordinates mystery-box, expedition and
challenge item grants with those same stack locks and database increments.
The caller keeps catalog eligibility, salvage and its reward receipt; the
grant commits or rolls back with the surrounding domain transaction.
`tests/test_inventory_grant_concurrency.py` exercises both last-item orders,
competing grants, automatic-goal lock order, retries and late failures on
PostgreSQL. Automatic goals lock only their activity row when joining user
and family data, preserving the existing user `NO KEY UPDATE` gate.

Legacy co-op quest advancement waits for an enclosing source transaction to
commit before taking all participant award locks in user ID order. This
avoids two source transactions holding opposing child locks while completing
the shared campaign. The callback keeps progress, every participant's payout
and completion notice atomic, and publishes its response only after success.
Source rollback discards it; solo quests and top-level game-loop calls remain
synchronous. Deferred failures follow the pipeline's existing logged,
best-effort policy and leave the quest retryable.

## Endpoints
- Staff-parent content workbench: `/api/rpg/content-workbench/` and its
  revisioned draft preview/simulate/publish endpoints. PostgreSQL stores private
  drafts and explicit published overrides; bundled YAML remains the baseline.
  Reuse the exact reviewed publication services and detached progression
  snapshots. Existing item behavior changes require a new version. See
  [`docs/operations/rpg-content-workbench.md`](../../docs/operations/rpg-content-workbench.md).
- Staff-parent design workbench: `GET /api/rpg/progression-lab/` and
  `POST /api/rpg/progression-lab/simulate/`. `progression/` snapshots only
  global supported content and runs bounded seeded scenarios in memory, with
  no real user selector or award writers. Reports explicitly describe their
  activity assumptions and omitted mechanics; finite-content projections are
  a modeled subset, not full-app exhaustion. See
  [`docs/operations/progression-lab.md`](../../docs/operations/progression-lab.md).
  Simulated hatch/evolution evaluates the pet and badge scopes at the same
  transition as live care. Reachable badges include obtainable companions,
  and the rules fingerprint binds the production care hooks. The projection
  keeps all awards in memory and never calls household award writers.
  Reports and metadata record `pet_incubation_policy`, including the installed
  elapsed duration and one unfinished slot. Ingredients are reserved during
  active care; readiness advances over inactive days, and the next active
  visit claims the egg before rewards and feeding. Pending eggs are not owned
  pets or completed targets. Policy changes invalidate model bindings without
  modifying historical report bodies. See the Lab guide for daily clock limits.
- Private feedback notebook: `/api/rpg/progression-lab/experiments/` saves
  author-and-family-scoped assumptions, immutable server-generated paired
  comparisons and append-only decisions with actions/review dates. It never
  publishes or changes rewards. Revisions plus engine/rules/catalog/evaluator
  bindings reject stale decisions; keep historical evidence readable even if
  today's catalog is unavailable. `progression/observations.py` separately
  reads bounded own-family recent-child ledger aggregates, with typed future
  attribution, incomplete-history coverage and insufficient empty cohorts.
  Preserve this separation from anonymous forecasts and MCP catalog scopes.
  `candidate_policy` selects the legacy payout envelope or fixed `commitment100`
  prototype. The latter reserves 75 expedition / 25 random-activity-pouch Coins
  before grants and pays established promises fully; boosts remain unmodeled.
  `expedition_budget` independently limits new launches and whole item promises
  shared across mounts. `expedition_limits` notebook candidates preserve identical
  Coin rules in both arms; the control has unlimited expedition quotas. Never
  conflate unavailable targets with additional runway or charge frozen claims
  against a later allowance. These are simulation policies, never live writers.
  `challenge_gates` overlays anonymous completion, named-skill, elapsed-tenure
  and calendar offering requirements. `current` ignores the recipe;
  `milestones` applies prerequisites/skills/calendar; `milestone_tenure` adds
  elapsed days from the first modeled visit. Gate notebook policies
  `milestone_gates` / `tenure_gates` retain identical Coin rules, expedition
  caps, recipe, seeds and catalog in both arms. Waiting active visits,
  structurally unreachable targets and expired windows remain separate from
  playable content. Never write these policies into live challenge definitions.
- `/api/sprites/catalog/` (`SpriteCatalogView`, public, ETag-cached) — read API.
- Compatibility admin endpoints at `/api/sprites/admin/*` remain in `sprite_admin_views.py`; Content catalog no longer exposes sprite administration.
- `POST /api/inventory/<item_id>/use/` — consume one consumable.
- `POST /api/character/trophy/` — set/clear the active trophy badge.
- `POST /api/character/avatar/` — replace the authenticated account's saved Archer appearance with strict supported options; returns the full character, defaults omitted options, and changes no earned state. See `avatar.py` and `tests/test_avatar.py`.
- `GET /api/cosmetics/` — owned cosmetics grouped by slot.
- `GET /api/cosmetics/catalog/` (child-accessible) — supported authored cosmetics grouped by slot keys; the retained `active_pet_accessory` key is an empty list. Non-cosmetic items are filtered server-side via `COSMETIC_SLOT_MAP.keys()`.

## Reading Adventure

Reading Adventure uses `TriggerType.READING_LOGGED` once per child per
family-local day after ten cumulative newly logged minutes. The reading
service's durable receipt commits its 15 base Reading Comprehension XP,
5 base Coins (`CoinLedger.Reason.READING`, Lucky Coin eligible), streak
activity and one drop opportunity together. Its drop rate is 0.20 before
normal streak/Drop Charm bonuses, using authored existing food and coin-pouch
pools. The service calls `GameLoopService.on_task_completed(..., strict=True)`
inside its outer transaction: any pipeline failure propagates so all reward
writes roll back. Existing callers retain the default independent-step
failure isolation. Awarded daily receipts provide explicit `reading_logged` Challenge facts keyed by
`reading_reward_id`, with the saved family-local day and award timestamp. Reading
does not count toward unfiltered effort goals or the daily effort bonus. Deleted
sessions retain their earned fact. Saved legacy quests retain filtering and
5 base boss damage. Default content loading installs the additive reading starter
and post-Full-Ark reading chapters atomically after the unchanged initial pack.
Both bundled packs live in `content/rpg/bundled/`, baked into the image; the
host bind mount over `content/rpg/packs/` would otherwise hide them at startup.

## Gotchas

- **Saved Archer appearance**: `CharacterProfile.avatar_preferences` is presentation independent from cosmetic slots and inventory. Hair/skin/outfit choices and defaults live in `avatar.py`: four hairstyles, five hair colors, two skin tones, four palettes, three independent costume styles, three faces and rounded/pointed ears. Optional wardrobe choices are headwear (`none`, `crown-eve`, `hood-mystical`), mask (`none`, `mask-undercover`), bow (`none`, `bow-greenhorn`, `bow-vines`, `bow-myth`) and quiver (`none`, `quiver-angel`, `quiver-rook`, `quiver-tale`), each defaulting to `none`. These are freely selected presentation preferences, without acquisition or earned unlocks. Character reads normalize empty/invalid legacy values without writes; older four-option looks retain their selections and project the default `archer-01` costume, `face-01` face and `head-02` pointed ears. Older seven-option looks retain their identity and project all four wardrobe fields to `none`. The avatar POST accepts exactly an `avatar_preferences` object, rejects unknown fields/types/values and query targeting, and atomically writes only `request.user`'s preferences/timestamp. Missing options reset to defaults; `{}` resets all eleven. An identical normalized retry changes nothing. No Coins, XP, streak, trophy, inventory or reward consumers run from an appearance save. Raw response fixtures are produced by `config/tests/test_avatar_api_contract_fixtures.py`. Saved choices do not certify private art preparation: rendering needs the corresponding reviewed runtime release in `docs/operations/licensed-avatar-art.md`.

- **RPG game loop**: `GameLoopService.on_task_completed(user, trigger_type, context)` is the single orchestrator called from all existing flows — clock-out (`apps/timecards/services.py`), chore approval (`apps/chores/services.py`), project/milestone completion signals (`apps/projects/signals.py`), homework create + approval (`apps/homework/services.py`), habit taps (`apps/rpg/views.py`), journal first-of-day (`apps/chronicle/services.py`), and creation first-2-per-day (`apps/creations/services.py`). Clock-out eligibility is source-owned: zero-minute closes skip the game loop; positive completed non-homework sessions record factual streak/quest activity, with one daily drop opportunity only after their cumulative completed time reaches 10 minutes. Splitting sessions cannot create extra rolls. Pipeline: (1) `StreakService.record_activity` updates `CharacterProfile.login_streak`, first-of-day action awards streak-scaled check-in coins (`5 × min(1 + streak × 0.10, 3.0)` — 5c at day 1, 15c cap at day 20+) via `CoinLedger.Reason.ADJUSTMENT`; (2) `DropService.process_drops` rolls against `BASE_DROP_RATES[trigger_type]` + streak bonus (`min(streak × 0.05, 0.50)`) — callers can set `context["drops_allowed"]=False` to suppress the drop roll while still recording streak + quest progress (used by `homework_created` to cap drops to the first log per day); (3) `QuestService.record_progress` applies damage/collection if the user has an active quest and the trigger matches the quest's `trigger_filter`. Returns `{trigger_type, streak, drops, quest, notifications}` — failures in quest progress are logged but never break the parent flow (wrapped in `try/except`). **`trigger_type` must be a value from `apps.rpg.constants.TriggerType`** — the same enum that backs `DropTable.TriggerType`, `BASE_DROP_RATES` (rpg/services), and `TRIGGER_DAMAGE` (quests/services). The content-pack loader validates `drops.yaml` triggers against it, so a typo raises `ContentPackError` before any write commits.

- **Streaks & daily engagement**: `CharacterProfile` auto-created per user via `post_save` signal on `accounts.User` (see `apps/rpg/signals.py`). `login_streak` resets to 1 on a gap > 1 day, increments on consecutive days, and is tracked alongside `longest_login_streak`. Milestone notifications fire once on the first activity reaching streaks of 3, 7, 14, 30, 60, 100 (`NotificationType.STREAK_MILESTONE`); repeated activities on that date do not repeat the celebration. **Perfect Day:** `evaluate_perfect_day_task` requires activity on the configured local worker/streak date (currently America/Phoenix), at least one eligible scheduled daily chore, and approved completions for every such chore. It awards the counter and 15 coins once per child/day through `PerfectDayReceipt`, including on concurrent/retried task delivery. The receipt, counter, coins, activity and notification commit together. Historical receipts preserve typed `system.perfect_day` evidence without rewriting rewards: an explicit event date takes precedence, otherwise the event timestamp is interpreted in America/Phoenix, the actual legacy producer policy; changing a family's timezone does not change those saved dates. See [`tests/test_perfect_day_integrity.py`](tests/test_perfect_day_integrity.py) and [`tests/test_perfect_day_receipt_backfill.py`](tests/test_perfect_day_receipt_backfill.py). **Streak Freeze:** `CharacterProfile.streak_freeze_expires_at` (DateField) is a one-shot grace set by consuming a `ItemType.CONSUMABLE` with `metadata.effect="streak_freeze"`. When `StreakService.record_activity` sees a gap > 1 day, it consumes the freeze if the expiry covers the first missed day — streak continues, field clears. Gentle-nudge design: missed days dim the streak flame visually and reset the multiplier, but NEVER destroy earned coins/XP/items.

- **Consumables**: `ItemType.CONSUMABLE` items fire a one-shot effect on use and decrement `UserInventory.quantity`. Dispatch lives in `ConsumableService._apply_effect` in `apps/rpg/services.py`, keyed by `metadata.effect` — unknown effects raise `ValueError` so a typo in YAML doesn't silently no-op. **14 effects ship today:** `streak_freeze` (protects one missed day; `metadata.duration_days`), `xp_boost` (Scholar's Draught — timer gate via `CharacterProfile.xp_boost_expires_at`; `metadata.duration_hours`), `coin_boost` (Lucky Coin — `coin_boost_expires_at`), `drop_boost` (Drop Charm — `drop_boost_expires_at`), `growth_tonic` (+2x growth for next N pet feeds; increments `CharacterProfile.pet_growth_boost_remaining`), `rage_breaker` (clears `Quest.rage_shield` on the user's active boss quest, erroring if none), `growth_surge` (Pet Evolution Accelerator — bolt of growth to active pet), `feast_platter` (+N growth to every unevolved pet), `mystery_box` (random common/uncommon non-cosmetic item), and **five added 2026-04-23**: `lucky_dip` (random uncommon-or-rarer cosmetic, auto-salvages dupes to coins), `quest_reroll` (spawns a random eligible system quest when user has no active quest), `morale_tonic` (+2x growth for next 5 feeds — longer-duration growth_tonic variant; distinct effect slug so `consumable_variety` counts it separately), `skill_tonic` (+N XP through the shared `AwardService` to the user's highest-level unlocked skill, including active XP boosts, prerequisite unlocks, badge evaluation and character-level synchronization), `food_basket` (N random food items). Boost multipliers are **fully wired** now: `xp_boost_multiplier(user)` in `apps/rpg/services.py` is called from `apps/achievements/services.py:275`; `coin_boost_multiplier(user)` from `apps/rewards/services.py:44` (via `is_boostable_coin_reason` whitelist — excludes refunds, redemptions, exchanges, and mixed-sign adjustments); `drop_boost_additive(user)` from `DropService.process_drops:258`. Timer gates + multipliers are pinned by `apps/rpg/tests/test_boost_multipliers.py`. Streak-freeze also increments `CharacterProfile.streak_freezes_used`, exposed as the `STREAK_FREEZE_USED` badge criterion. Endpoint: `POST /api/inventory/<item_id>/use/` accepts an optional `quantity` body field (default `1`); stack-safe effects (counters / random rolls / additive XP — `mystery_box`, `lucky_dip`, `food_basket`, `growth_tonic`, `morale_tonic`, `skill_tonic`, `feast_platter`) loop the apply path N times, while stack-unsafe effects (timer overwrites + single-target — `xp_boost`, `coin_boost`, `drop_boost`, `streak_freeze`, `rage_breaker`, `growth_surge`, `quest_reroll`) reject `N > 1` with 400 (the second use would clobber the first timer or no-op against an already-cleared shield). The classification lives in `_STACK_SAFE_EFFECTS` in `apps/rpg/services.py`. Adding a new consumable means (a) seed entry in `content/rpg/initial/items.yaml` with `item_type: consumable` + `metadata.effect: <slug>`, (b) new branch in `_apply_effect`, and (c) decide whether to add the slug to `_STACK_SAFE_EFFECTS`. **Active boost timers** are exposed on `CharacterProfileSerializer` (`xp_boost_expires_at` / `coin_boost_expires_at` / `drop_boost_expires_at` / `pet_growth_boost_remaining`) so the frontend [`BoostStrip`](/frontend/src/components/rpg/BoostStrip.jsx) can render `1h12m left` chips on Inventory + the Sigil Frontispiece — kids no longer have to guess whether their potion is still working. Frontend `Inventory.jsx` renders a "Use" button on any `item_type: consumable` card; cards with `stack > 1` AND a stack-safe effect get a `−/+/all` quantity stepper plus a `Use × N` label.

- **Drops & inventory**: `ItemDefinition` is the master catalog (10 item types: egg, potion, food, cosmetic_frame, cosmetic_title, cosmetic_theme, cosmetic_pet_accessory, quest_scroll, coin_pouch, consumable; 5 rarities). Cross-entity references are typed: `ItemDefinition.pet_species` FK (eggs → `PetSpecies`), `ItemDefinition.potion_type` FK (potions → `PotionType`), `ItemDefinition.food_species` FK (food → preferred `PetSpecies`). `metadata` JSONField stays for genuinely free-form per-type fields (border colors, title text, coin-pouch counts). `DropTable` maps trigger → item → weight with `min_level` gating. `DropService.process_drops` rolls `random.random()` against effective rate, weighted-selects from eligible rows, handles **cosmetic salvage** (already-owned cosmetics auto-convert to coins via `item.coin_value`), increments `UserInventory.quantity`, and logs to `DropLog`. Frontend `useDropToasts` polls `/api/drops/recent/` every 20s and emits rarity-colored toast celebrations via `DropToastStack` (mounted globally in Layout).

- **Cosmetics**: `CharacterProfile` retains 4 nullable FK slots (`active_frame`, `active_title`, `active_theme`, `active_pet_accessory`) with `limit_choices_to={"item_type": ...}` enforcing correct type. `CosmeticService.equip(user, item_id)` validates inventory ownership and current catalog availability, then writes the correct slot without consuming the item. `CosmeticService.unequip(user, slot)` clears optional slots, including an earlier accessory selection. Legacy cover removal restores `User.theme=hyrule` and selects an existing owned supported default cover when available, otherwise leaving the FK null; it never grants inventory or rewards. Legacy `/auth/me/` theme PATCH resolves palette aliases and selects only an owned supported cover through the equip service; invalid or unowned themes return 400 without changes. Duplicate supported cosmetic drops auto-salvage (see Drops gotcha). `GET /api/cosmetics/` retains owned cosmetics grouped by slot; `GET /api/cosmetics/catalog/` returns supported authored cosmetics in the same shape so Profile can show unowned Frames/Titles as goals and Settings can select owned Covers. Inventory cover actions link to `/settings#appearance`; other identity cosmetics link to Profile. The accessory slot remains an empty catalog list. Non-cosmetic items are filtered server-side via `COSMETIC_SLOT_MAP.keys()`; malformed cover metadata still fails existing validation.

- **Trophy shelf** (`CharacterProfile.active_trophy_badge`, added 2026-04-23; frontend picker wired 2026-04-22): optional "hero badge" FK the user elects to display on their profile. Endpoint `POST /api/character/trophy/ {badge_id}` — the server enforces that the user has **earned** the badge (via `UserBadge`) before setting, so parent-authored or admin-forced trophies can't bypass the "earn it first" rule. Pass `badge_id: null` to clear. Exposed on `CharacterProfileSerializer` as `active_trophy_badge` (compact `{id, name, icon, rarity, description}` shape). FK uses `on_delete=SET_NULL` so archiving badges doesn't break profiles. Picker UI lives in [`TrophyBadgePicker`](/frontend/src/pages/character/TrophyBadgePicker.jsx) — a `BottomSheet` that reuses the Reliquary Codex's `groupBadgesByCollection` filtered to earned-only, so the seven-chapter grouping at `/atlas?tab=badges` is the same grouping you see when choosing your hero seal.

- **Prepared sprite artwork**: AI sprite generation was retired on October 17, 2026. There is no generation, reroll, prompt-refinement or playbook implementation, Gemini configuration, or image-generation SDK. The former REST generation/reroll POST URLs return JSON HTTP 410 to authenticated staff parents. Keep existing `SpriteAsset` rows, files, animation metadata and historical authoring fields readable. New artwork is prepared outside the application and can be registered through the staff-only MCP `register_sprite`, `register_sprite_batch` and `register_sprite_assets` tools. Do not reintroduce provider calls into the sprite path.

- **Content catalog** (`/codex`): the parent reference page contains Items, Pet species, Grown pets and Challenges. The obsolete Sprites section and its metadata/deletion sheets are removed; the page does not request `/api/sprites/admin/`. A remembered Sprites selection falls back to Items. Compatibility endpoints remain: `GET /api/sprites/admin/` is a parent-only catalog read; `PATCH` and `DELETE /api/sprites/admin/<slug>/` require `IsStaffParent`. Legacy prompt/reference fields are historical metadata, not a private family content store.

- **Runtime sprite presentation**: `RpgSprite.jsx` tries prepared companion-roster portraits and licensed portraits before the runtime sprite catalog, with image-error and emoji fallback. `SpriteAsset` stores slug, image, pack and animation metadata. Static sprites have `frame_count=1` and `fps=0`; animated sprites require positive fps. Prepared PNG/WebP uploads use the separate public sprite storage backend and content-hash filenames; family media stays on the private default storage backend. Registration validates and uploads replacements before switching the database record; old-file cleanup follows a successful commit. Catalog reads remain public and ETag-cached, with animation metadata and reduced-motion support. See [asset preparation guidance](../../content/rpg/react-three-fiber-assets.md) for current models and portraits.

- **RPG content authoring** (`content/rpg/`): Pets, eggs, potions, items, drops, quests, badges, and the skill tree are authored as YAML in `content/rpg/initial/*.yaml` and loaded by `python manage.py loadrpgcontent` — a dependency-ordered, idempotent upsert. `seed_data` invokes this internally. The loader (`apps/rpg/content/loader.py`) is the single source of truth for cross-entity wiring: one `pet_species.yaml` entry fans out to both a `PetSpecies` row and an egg `ItemDefinition` with typed FK; same pattern for `potion_types.yaml` → potion items. Third-party packs live under `content/rpg/packs/<name>/` and are loaded with `--namespace <prefix>-` so slugs don't collide with core. When adding new RPG content, edit YAML — don't add `get_or_create` calls to Python seed code. See `content/rpg/README.md` for schema + authoring workflow.

  Unkeyed deployment loads seed missing shop offers into the explicit legacy
  `default-family` destination (or the supplied family), preserving every
  existing offer and parent edit. Names do not establish seed ownership, so
  later bundled price/approval changes intentionally do not overwrite these
  rows; reviewed pack publications retain their explicit owned-update path.
  Duplicate legacy drop or quest-item links are preserved and reported as
  ambiguous without blocking startup. Reconcile them explicitly to apply
  bundled link updates; the loader never guesses which quantity or weight is
  authoritative. Reviewed publications still reject ambiguous links and roll
  back the entire publication. `tests/test_startup_loader_safety.py` covers
  these boundaries through the actual loader and startup command.

## RPG tunables (hardcoded constants in `apps/rpg/services.py`)
These are intentionally NOT in settings — they're game-design constants, not deploy-time config.
- `BASE_CHECK_IN_COINS = 5` — base daily check-in bonus before streak multiplier.
- `STREAK_MULTIPLIER_PER_DAY = 0.10` and `STREAK_MULTIPLIER_CAP = 3.0` — check-in bonus scales `min(1 + streak × 0.10, 3.0)` (5c at day 1, 15c cap at day 20+). Bumped 2026-04-23 from 0.07 so the cap reaches at ~3 weeks instead of ~4.
- `BASE_DROP_RATES` — dict of `TriggerType` → base drop probability (clock_out 0.40, chore_complete 0.30, homework_complete 0.35, homework_created 0.15, milestone_complete 0.80, project_complete 1.00, badge_earned 1.00, quest_complete 1.00, perfect_day 1.00, habit_log 0.15, savings_goal_complete 0.80, journal_entry 0.20, creation_logged 0.25). `journal_entry` was bumped from 0.10 → 0.20 in the 2026-05 progression-UX pass — the DB unique constraint on `(user, occurred_on) where kind=journal` already throttles journals to one per local day, so a higher rate is fairness-rebalancing against `habit_log` (which can fire 4+ taps/day at 0.15) rather than a farm risk. Clock-out separately has one drop opportunity per family-local day after 10 cumulative completed non-homework minutes; zero-minute closes cannot enter the game loop. Three other triggers are daily-capped at the service layer: `homework_created` (first-of-day only via `HomeworkDailyCounter`), `journal_entry` (one per local day, DB-enforced via partial unique constraint on `ChronicleEntry`), and `creation_logged` (first 2 per local day via `CreationDailyCounter`). The two counter-backed gates share the `config.base_models.DailyCounterModel` abstract + `config.services.bump_daily_counter` helper. All three close streak/drop/quest farming at source — counter rows survive both soft-delete and hard-delete, so collusion-style resets (create → delete → create) don't re-arm.
- `STREAK_DROP_BONUS_PER_DAY = 0.05` and `STREAK_DROP_BONUS_CAP = 0.50` — streak adds up to +50% to base drop rate.

## Key entry points
- `services.py` — `GameLoopService.on_task_completed` (single entry point), `StreakService`, `DropService`, `ConsumableService`, `CosmeticService`, `_BOOSTABLE_COIN_REASONS`, `_STACK_SAFE_EFFECTS`, boost-multiplier helpers.
- `signals.py` — `post_save` on `accounts.User` creates `CharacterProfile`.
- `constants.py` — `TriggerType` TextChoices (the canonical enum).
- `sprite_authoring.py` — `register_sprite` + sibling write paths.
- `sprite_admin_views.py` — parent-only admin CRUD endpoints.
- `content/loader.py` — RPG YAML loader, with strict pack-owned authoring and retained legacy CLI behavior.
- `content/publication.py` — expiring exact-source/state plans, PostgreSQL catalog serialization and atomic audited publication. Shop destinations are explicit families; stable provenance protects cross-pack collisions. Retain accepted quest snapshots before reconciling reward links. See [MCP authoring](../../docs/operations/mcp-authoring.md).
- `content/validation.py` — shared strict authoring shape, trigger, range and badge-condition validation.
- `ConsumableService.SUPPORTED_EFFECTS` in `services.py` — canonical effect names shared by runtime dispatch and catalog audits; handler tests keep them aligned.
- Design spec: `docs/superpowers/specs/2026-04-13-rpg-gamification-layer-design.md`.

Prepared roster adoption registers 14 namespaced families plus Chick, all
Base-only under the current acquisition registry. The content loader rejects
existing identity collisions before upserts and applies the namespace once.
`companion_catalog.py` reconciles stale egg/potion drop configuration and digital
shop offers idempotently; it never deletes item/species definitions, quest reward
links or frozen promises. Use `reconcile_companion_catalog --dry-run --json`
before rollout. Egg-category weights remain unchanged in live selection. See
[the adoption runbook](../../docs/operations/companion-lifecycle.md).

`retired_catalog.py` owns the exact owner-approved prelaunch retirement list.
Default `loadrpgcontent` attempts it once before bundled upserts and records
`RPGContentRetirement.applied_at` in the same transaction. Later startup loads
skip a completed transition rather than continually deleting newly authored
content. Explicit custom-pack loads do not run it. Changed identity, protected
reference or resource-validation conflicts roll back the entire retirement
savepoint, emit a warning and continue ordinary bundled loading without a
success marker. The standalone `retire_unused_rpg_content` command is strict;
`--dry-run --json` previews exact catalog/dependent IDs, cascades and settlements.

Before removing obsolete ownership and receipts, `retirement_resources.py`
refunds the net recorded Coin holds for pending/approved undelivered digital-only
redemptions, returns matching supported ingredients from an unfinished accepted
incubation, and settles ACTIVE unclaimed deleted-mount expeditions from their saved Coins
and surviving supported item loot. This does not roll new rewards, apply current
boosts, grant XP/badges or run the game loop. Existing ledger entries remain;
new refund/settlement entries can increase balances. Deletion and settlement
commit together, so retry cannot pay twice.

Cleanup prunes only the exact retired JSON reward/loot slots and clears their
equipped references. An edited obsolete digital offer with a supported frozen
promise retains that receipt and is deactivated. Real-world and combined offer
rows survive with the obsolete optional item FK cleared. Combined offers are
deactivated and converted to real-world fulfillment; their frozen combined
receipts retain status, cost, audit and actual debits as real-world promises,
without a refund, so physical delivery remains possible. Current fifteen
families, Base/Fire/Ice, unknown/custom identities, accounts, generic SpriteAsset
registration/rows and image storage
are outside the list. No old species is migrated into a different new family.
Default-loader dry runs and later bundled-load failures roll back the marker,
settlement and cleanup together. See the adoption runbook for the exact scope;
this implementation does not establish a production release.
