# Manual Testing — Random & Conditional UI Checklist

The Abby Project has accumulated a long tail of UI surfaces that only render
under specific conditions: celebration modals, rare drop reveals, streak
flames, journal lock states, low-stock chips, OOS suggestion sheets, partial-
failure retry banners, per-rarity halos, etc. Regular dev-loop testing reaches
maybe 20–30% of them. This document enumerates the rest.

This is the **spine**. The companion management commands under
`apps/dev_tools/management/commands/` (Phase 2 of the testing strategy) are
designed to drive each of these surfaces directly. Where a command exists, its
name is in `code` font in the trigger column. Where one doesn't yet, `(manual)`
notes the precondition and you set it up by hand.

**How to use this:**
1. Spin up dev (`docker compose up --build` or local) with `DEBUG=True`.
2. Login as a parent or seed-test child as the row needs.
3. Walk top to bottom — most rows take < 30 seconds.
4. When something doesn't render or renders wrong, file it.

A clean pass should take 60–90 minutes. Run it before every release tag.

---

## A. Celebration overlays / modals

Full-screen or center-screen reveals that block interaction. Easy to break in
ways that "looks fine on the dashboard" doesn't catch.

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| `CelebrationModal` (streak milestone) | Unread `STREAK_MILESTONE` notification at one of {3, 7, 14, 30, 60, 100} days | `force_celebration --user X --type streak_milestone --days 30` | Full-screen at App boot. Flame icon. "30 day streak!" Reload-once dismiss. Auto-marks notification read on close. |
| `CelebrationModal` (perfect day) | Unread `PERFECT_DAY` notification | `force_celebration --user X --type perfect_day` | Full-screen. Sun icon. "Perfect day" copy. Same dismiss flow. |
| `BirthdayCelebrationModal` | Unread `BIRTHDAY` chronicle entry with `metadata.gift_coins > 0` | `force_celebration --user X --type birthday` (or `tick_chronicle_birthday --user X --as-of <DOB>`) | Animated age numeral burst (unless reduced-motion). Gift-coins line. Confetti. `mark-viewed` on dismiss. |
| `RareDropReveal` (rare) | Drop with `item_rarity=rare` enters the queue | `force_drop --user X --rarity rare` | Center card. **Blue** border + 60px glow. "RARE DROP" label. 96px sprite. Continue → button. |
| `RareDropReveal` (epic) | `item_rarity=epic` | `force_drop --user X --rarity epic` | **Purple** border + 70px glow. |
| `RareDropReveal` (legendary) | `item_rarity=legendary` | `force_drop --user X --rarity legendary` | **Amber** border + 70px glow. |
| `RareDropReveal` (queue) | 2+ rare-tier drops back-to-back | `force_drop … --count 3 --rarity epic` | Each shows in sequence — second can't preempt the first. |
| `DailyChallengeClaimModal` | Today's `DailyChallenge` is complete + unclaimed | (manual: complete a daily challenge) | Sun icon. "Rite complete" headline. "+coins · +xp" displayed. Lucky Coin doubles coins (regression — historic bug shipped without doubling). |
| `PetCeremonyModal` (hatch) | Pet just hatched (mode=`hatch`) | `force_pet_hatch --user X --species Y` | Sparkle reveal. Species sprite. "has joined your party". Tap-anywhere dismiss. |
| `PetCeremonyModal` (evolve) | Pet just evolved (mode=`evolve`) | `force_pet_evolve --user X --pet Y` | Crown halo. Mount sprite (uses `{species}-mount` slug; falls back to base species sprite if not in catalog). "is ready to ride". |

---

## B. Toast stacks

Slide-in / floating notifications. Stack at different `top-N` heights so
multiple can show simultaneously.

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| `DropToastStack` (common/uncommon) | Drop with rarity NOT in {rare, epic, legendary} | `force_drop --user X --rarity common` | Top-right (top-4). Rarity-bordered. Package icon + sprite + name. Auto-dismiss 6s. |
| `DropToastStack` (salvage) | Cosmetic dupe drops | `force_drop --user X --slug <owned-cosmetic>` | Toast text reads "Salvaged" (NOT "You got"). Coin value reflects `item.coin_value`. |
| `ApprovalToastStack` | Pending approval gets approved/rejected (child-side) | (manual: parent approves a chore) | Top-36 (below DropToastStack). CheckCircle2 (green) for approve, XCircle (rose) for reject. 2-line message clamp. |
| `ApprovalToastStack` (reject with note) | Reject with non-empty note | (manual: parent reject sheet with note) | Toast body includes the note text. Pinned by approval-flow regression — silent rejects pre-`307e6aa` are how this surface broke. |
| `QuestProgressToastStack` | Active quest's `current_progress` increments | (manual: contribute to active quest) | Top-52. Sword icon. "+10 toward Dragon Slayer 62%". Auto-dismiss 4s. |
| `SavingsToastStack` | Savings goal completion | `force_savings_complete --user X --goal Y` | Top-20. Trophy icon + amber. "Hoard complete!" + bonus coin amount. |
| `OfflineReadyToast` | Service worker first precache finishes | (manual: hard-reload in production-like build) | Bottom-right one-shot. CheckCircle2 + "Ready to work offline." 4s auto-dismiss. |
| Equip toast (Character) | Cosmetic equip/unequip | (manual: click an owned cosmetic on `/sigil`) | Bottom-floating "Now wearing X". framer-motion floater. ~3s lifetime. |

**Compound case:** Simultaneous drop + approval + quest progress should stack
without overlapping (different `top-N` heights). Reproduce by approving a chore
that completes a quest objective and grants a drop in the same backend call.

---

## C. Banners / sticky chips

Persistent UI that appears only in narrow states.

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| `UpdateBanner` (PWA) | Service worker has a `waiting` state | (manual: deploy a new build, refresh) | Sticky top, sheikah-teal, "New version available." + Reload link. Reload survives the iOS Safari `controllerchange` quirk via the 1.5s setTimeout fallback. |
| `ErrorAlert` + Retry (parent dashboard) | At least one of 5 approval-queue fetches errored | `inject_failure --queue chore --status 500` | Banner above ApprovalQueueList. Lists the failed source label ("chore approvals"). Retry button re-fans. Auto-clears within `--ttl` seconds. |
| Low-stock chip (`stock=1`) | Reward stock crosses to 1 | `set_reward_stock --reward Y --stock 1` | "last one" copy in ember tone on RewardCard. |
| Sold-out chip (`stock=0`) | Reward stock = 0 | `set_reward_stock --reward Y --stock 0` | "sold out" copy in ember tone, button disabled. |
| Insufficient-coins pre-flight | `reward.cost > balance` AND user clicks redeem | (manual: redeem a too-expensive reward) | Inline chip "Not enough coins yet — need 12 more (cost: 50, you have 38)." NO backend round-trip. |
| Boost timer chips | At least one of `xp_boost_expires_at` / `coin_boost_expires_at` / `drop_boost_expires_at` / `pet_growth_boost_remaining` is active | `gift_inventory --user X --slug lucky-coin && consume it` | `BoostStrip` row on Inventory + Sigil Frontispiece. Live countdown updates every 1s. Renders null when no boosts. |
| Header progress band | User has an active quest | (manual: start any quest) | Thin sheikah-teal gradient band under header, scaled to `progress_percent`. Inert when no active quest. |
| FAB running-timer chip | User is clocked in | (manual: clock in) | QuickActionsFab shows live timer. Persists across page nav. |
| Can-self-plan disabled | Child views their own homework with `due_date < today + HOMEWORK_SELF_PLAN_LEAD_DAYS` | `lock_homework_self_plan --user X` | "Plan it out" button missing or disabled. Parent always sees it. |

---

## D. Empty states

Each empty state has role-aware copy. Easy to test the "happy" path and miss
that the empty path renders blank.

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| `NoChildrenWelcome` (parent) | `children_count === 0 AND pending.length === 0` | (manual: fresh parent) | UserPlus icon, "Welcome — let's add your first kid", deep-link to `/manage`. Hidden once any child or pending row exists. |
| RewardShop empty (child) | No rewards in family | (manual: parent deletes all rewards) | "ask a parent to add some" copy. |
| RewardShop empty (parent) | Same precondition viewed as parent | (manual: same) | "head to Manage to add some" copy. Different from child. |
| Sigil load failed | `getCharacterProfile()` returns null | (manual: hard to hit; mock failure) | "Unable to load sigil." EmptyState. |
| Catalog search empty (Inventory) | Inventory has ≥1 item AND search yields 0 matches | (manual: type "qzqzqz" in Inventory search) | EmptyState w/ "no matches — clear the filter" copy. Distinguishable from "no items yet". |
| Catalog search empty (Badges) | Same shape, Reliquary chapter | (manual) | Same per-page copy. |
| Catalog search empty (Skills) | Same shape, folio | (manual) | Drops empty subjects. |
| Catalog search empty (Rewards) | Same shape, Bazaar | (manual) | EmptyState with clear-filter hint. |

---

## E. Lock / read-only states

UI that exists but disables all editing.

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| Journal entry locked (read-only modal) | Try to open a journal entry where `entry.occurred_on !== today` | `expire_journal --user X` then open via `/yearbook` | Title flips to "Journal entry — locked". Lock-icon chip. Title + body fields disabled. Only Close button (no Update). |
| Journal entry locked (403 fallback) | Day rolls over while modal is open + click Save | (manual: open modal at 11:59pm, wait 2min, click save) | Toast: "that entry is locked now — part of your chronicle." 403 caught from `PATCH /api/chronicle/{id}/journal/`. |
| QuestLogEntry locked | Status === `locked` | (manual: in-quest precondition) | Inset dimmed row. Check button disabled with `cursor-not-allowed`. |
| Cosmetic intaglio (locked) | Cosmetic in catalog NOT in user's inventory | (manual: any new user — un-owned cosmetics auto-show locked) | Debossed ring + dashed border + grayscale sprite. Unlock hint underneath ("Earn the Polymath badge", etc.). NOT clickable; no equip on focus/click. `aria-label` ends "· not yet earned". |
| Skill locked (prereq) | Skill has unmet `SkillPrerequisite` | (manual: open a category with prereq tree) | Grayscale icon + no progress bar in `SkillVerse`. PrereqChain shows the chain. |
| Skill locked (max level) | Skill at level 6 | (manual: max out a skill via clock-out grind, or `set_streak` won't help — XP grant via dev tool) | Same dim treatment + "Mastered" copy. |

---

## F. OOS / fallback / degradation paths

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| Reward 409 + similar suggestions | Stock=0 + click redeem | `set_reward_stock --reward Y --stock 0` then redeem | Modal: original reward at top, list of similar (same rarity → cost band fallback) below. "notify me" wishlist toggle present. |
| Insufficient-coins inline error | `reward.cost > balance` | (manual) | Inline error chip above RewardShop, button label changes from Barter → "Need X more". |
| Mount sprite fallback | `{species}-mount` not in sprite catalog | (manual: pick a species with no mount sprite) | Falls back silently to base species sprite. Verify via `data-sprite-key` attr. |
| Sprite catalog miss (emoji fallback) | RpgSprite for unknown slug | (manual: pass unknown sprite key) | Renders `item.icon` emoji. |
| Wishlist restock | Parent edits a reward and stock crosses 0 → ≥1 | `set_reward_stock --reward Y --stock 5` (after a wishlist user added it) | `REWARD_RESTOCKED` notification fires once per wishlist user. Wishlist rows clear in same transaction (next stock cycle won't re-spam). |

---

## G. Per-rarity / per-state visual variants

Small differences that often regress silently when shared component code
changes.

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| Badge gilded glint | Earned within last 7d | `force_badge --user X --slug Y` | `animate-gilded-glint` foil sheen. Disappears at day 8. |
| Badge halo | Earned, gilded tier | (same as above + check `RARITY_HALO[badge.rarity]`) | Per-rarity colored shadow ring. |
| Pet happiness `bored` | `last_fed_at` 4–7 days ago | `set_pet_happiness --user X --level bored` | grayscale(0.25) + opacity(0.85) on sprite. Whisper line: "a little bored — feed me?" |
| Pet happiness `stale` | 8–14 days | `set_pet_happiness --user X --level stale` | grayscale(0.5) + opacity(0.7). Whisper: "getting hungry — needs a snack". |
| Pet happiness `away` | > 14 days | `set_pet_happiness --user X --level away` | grayscale(0.75) + opacity(0.55). NO whisper line (intentional — sprite already carries the signal). |
| Pet happiness `happy` (evolved) | Pet `evolved_to_mount=True` | (manual: any mount) | NO dim + NO whisper, regardless of `last_fed_at`. |
| Boost timer countdown | Active boost | `gift_inventory --user X --slug xp-boost && consume` | `BoostStrip` chips tick every 1s. Live count visible. |
| Streak flame size tier | `login_streak` ∈ {1, 7, 30, 100} | `set_streak --user X --days 30` | Flame size visibly larger on `/sigil` per `streakTier()` ladder. |
| Theme cover hover preview | Hover swatch in Settings (not reduced-motion) | (manual: hover swatches) | `applyTheme()` flashes whole-page skin. `mouseleave/blur` restores. Reduced-motion users never see the flash. |
| Cosmetic equipped halo | Cosmetic in `active_<slot>` FK | (manual: equip a cosmetic) | `RARITY_HALO` glow + "equipped" gilt ribbon. |
| Cosmetic owned (un-equipped) | Cosmetic in inventory, not in active slot | (manual) | Clean rarity ring, no halo. |

---

## H. Notification bell

25 distinct `NotificationType` values, each with its own icon + accent + default
route. The parity test (`notifications.constants.test.js`) gates new backend
types against frontend coverage — but visual regression on any single type can
still ship.

| Type | Icon | Accent | Default route |
|---|---|---|---|
| `badge_earned` | Award | gold | `/atlas?tab=badges` |
| `skill_unlocked` | Star | gold | `/atlas?tab=skills` |
| `milestone_completed` | Hammer | teal | `/projects` |
| `project_approved` | Hammer | moss | `/projects` |
| `project_changes` | Hammer | ember | `/projects` |
| `chore_submitted` | ListChecks | teal | `/quests?tab=duties` |
| `chore_approved` | ListChecks | moss | `/quests?tab=duties` |
| `chore_rejected` | ListChecks | ember | `/quests?tab=duties` |
| `chore_proposed` | ListChecks | teal | `/quests?tab=duties` |
| `chore_proposal_approved` | ListChecks | moss | `/quests?tab=duties` |
| `chore_proposal_rejected` | ListChecks | ember | `/quests?tab=duties` |
| `homework_created` | BookOpen | teal | `/quests?tab=study` |
| `homework_submitted` | BookOpen | teal | `/quests?tab=study` |
| `homework_approved` | BookOpen | moss | `/quests?tab=study` |
| `homework_rejected` | BookOpen | ember | `/quests?tab=study` |
| `homework_due_soon` | Hourglass | ember | `/quests?tab=study` |
| `timecard_ready` | Hourglass | teal | `/timecards` |
| `timecard_approved` | Hourglass | moss | `/timecards` |
| `payout_recorded` | Coins | gold | `/payments` |
| `redemption_requested` | Gift | teal | `/rewards` |
| `exchange_requested` | Coins | teal | `/rewards` |
| `exchange_approved` | Coins | moss | `/rewards` |
| `exchange_denied` | Coins | ember | `/rewards` |
| `low_reward_stock` | AlertTriangle | ember | `/manage` |
| `reward_restocked` | Gift | gold | `/rewards` |
| `streak_milestone` | Flame | ember | `/sigil` |
| `perfect_day` | Sparkles | gold | `/sigil` |
| `daily_check_in` | Sparkles | teal | `/sigil` |
| `drop_received` | Backpack | gold | `/inventory` |
| `quest_completed` | Trophy | gold | `/quests` |
| `pet_evolved` | PawPrint | gold | `/bestiary?tab=companions` |
| `mount_bred` | Crown | gold | `/bestiary?tab=mounts` |
| `savings_goal_completed` | Coins | gold | `/projects` |
| `birthday` | Cake | gold | `/yearbook` |
| `chronicle_first_ever` | ScrollText | teal | `/yearbook` |
| `comeback_suggested` | Footprints | teal | `/today` |
| `creation_submitted` | Palette | teal | `/atlas?tab=sketchbook` |
| `creation_approved` | Palette | moss | `/atlas?tab=sketchbook` |
| `creation_rejected` | Palette | ember | `/atlas?tab=sketchbook` |

**How to walk:** `force_notification --type <NotificationType>` once per row,
then check the bell — verify icon, accent, and that clicking routes to the
expected page. Unknown types should fall back to `BellRing` + null route, NOT
crash.

---

## I. Approval flows (parent surface)

The matrix of submit → approve/reject side-effects. Easy to break in subtle
ways: silent rejection, wrong notification type, XP doubled but coins
not (the historic Lucky Coin / Daily Challenge bug shape).

| Approval | Approve fires | Reject fires | Verify |
|---|---|---|---|
| Chore | XP + coins; `CHORE_APPROVED`; drops; quest progress; badge eval | `CHORE_REJECTED` (was silent pre-`307e6aa`); reject note woven into body | Reject WITH note → kid sees note in bell. Reject WITHOUT note → no note. |
| Homework | Skill XP; `HOMEWORK_APPROVED`; drops; quest progress; badge eval | `HOMEWORK_REJECTED`; note in body | No money/coins on homework — XP only. |
| Reward redemption | `redemption.status = fulfilled`; coin held → final | Coins refunded via `CoinLedger.REFUND`; stock restored | Refund must show in coin breakdown. |
| Exchange | Money debit + coin credit atomically; `EXCHANGE_APPROVED` | `EXCHANGE_DENIED`; no ledger side-effects | Re-verify balance at approval time, NOT request time. |
| Creation bonus | +15 XP via `CreationBonusSkillTag` (or primary fallback); `CREATION_APPROVED` | `CREATION_REJECTED`; baseline XP NOT reversed | Baseline XP from log_creation stays even on bonus reject. |
| Timecard | Status flip + email | (no UI reject path; void instead) | Approval is single-step; void uses different endpoint. |
| `Approve all (N)` | Per-kid bulk fanout via `Promise.allSettled` | n/a | Visible only when single kid has ≥2 pending. > 3 prompts ConfirmDialog. Failures stay visible with error chip. |

---

## J. Scheduled Celery tasks

Tasks that produce visible UI overnight. Hard to test by waiting; the `tick_*`
commands run them synchronously with `--as-of` for date simulation.

| Task | Schedule | UI / state produced | Force command |
|---|---|---|---|
| `auto_clock_out_task` | Every 30 min | Auto-completes long-running TimeEntry | (manual) |
| `generate_weekly_timecards_task` | Sun 23:55 | One Timecard per child for prior week | (manual) |
| `evaluate_perfect_day_task` | Daily 23:55 | `PERFECT_DAY` notification + 15 coins if all daily chores done AND has ≥1 daily chore scheduled | `tick_perfect_day --user X` |
| `decay_habit_strength_task` | Daily 00:05 | Habit `strength` decays toward 0 by step | `tick_habit_decay` |
| `expire_quests_task` | Daily 00:10 | Past-due active quests → status=expired | `tick_quest_expire` |
| `apply_boss_rage_task` | Daily 00:15 | Idle-day climb +15, active-day decay −25 (cap 100) | `tick_boss_rage` |
| `chronicle_birthday_check` | Daily 00:20 | `BIRTHDAY` chronicle entry + coins (per `BIRTHDAY_COINS_PER_YEAR × age`) | `tick_chronicle_birthday --as-of YYYY-MM-DD` |
| `chronicle_chapter_transition` | Daily 00:25 | `CHAPTER_START` (Aug 1) / `CHAPTER_END` (Jun 1) + freeze RECAP; grade-12 emits standalone `graduated_high_school` | `tick_chronicle_chapter --as-of` |
| `rotate_daily_challenges_task` | Daily 00:30 | Today's `DailyChallenge` row per active child | `tick_daily_challenge_rotation` |

---

## K. Random-roll surfaces

Non-deterministic paths. Re-run each 5–10× and confirm the distribution
"feels" right; the dev panel doesn't fix the randomness, but the `force_*`
commands let you bias outcomes.

| Surface | File:Line | What's random | Verify |
|---|---|---|---|
| Drop probability roll | `apps/rpg/services.py:314` | `random.random()` vs effective_rate | Streak bonus + drop boost both modify rate. Re-run with `force_drop` to bypass. |
| Drop item selection | `apps/rpg/services.py:354` | Weighted `random.choices(weights=…)` | DropTable weights honored. |
| Pet drops | `apps/rpg/services.py:979` | Weighted | Eligible pool respects min_level. |
| Mount drops | `apps/rpg/services.py:1009` | Weighted | Same. |
| Mystery box | `apps/rpg/services.py:1053` | Random uncommon-or-rarer cosmetic | Auto-salvages dupes. |
| Food basket | `apps/rpg/services.py:1103` | N items rolled | N=stack count. |
| Daily challenge template | `apps/quests/services.py:628` | `random.choice` from `DAILY_CHALLENGE_TEMPLATES` | Five types rotate. |
| Mount breeding species | `apps/pets/services.py:396` | Random from {parent_a, parent_b} | 50/50. |
| Mount breeding potion | `apps/pets/services.py:397` | Same | 50/50. |
| Chromatic upgrade | `apps/pets/services.py:400` | `random.random() < 0.02` | 2% chance overrides potion to Cosmic regardless of parents. |

---

## L. Salvage paths

Two distinct toast/UI shapes from "got an item" — easy to miss because they
share an endpoint with the regular drop/quest reward path.

| Surface | Precondition | How to trigger | Verify |
|---|---|---|---|
| Egg salvage (quest reward) | Quest reward includes an egg whose `pet_species` already exists in `UserMount` | `gift_egg_dupe --user X --species Y` then complete a quest with that egg as reward | `rewards["items"]` entry has `salvaged_to_coins`. Coin payout = `coin_value × qty`. |
| Cosmetic dupe salvage (drop) | Drop rolls a cosmetic the user already owns | `gift_cosmetic_dupe --user X --slug Y` then `force_drop --user X --slug Y` | `was_salvaged=True` on the toast. Coin value awarded. NO inventory dupe. |

---

## M. Compound preconditions

These are the ones that bit us in production — multiple conditions stacked
that can't be reproduced without specific orchestration.

1. **Low-stock chip via redemption**: chip fires only when reward stock crosses
   `0→1` *via a redemption event* AND a parent is currently viewing Rewards
   page. Setup: `set_reward_stock --reward Y --stock 2`, then have a child
   redeem twice. Watch the parent view tick down.
2. **Journal lock race**: open `JournalEntryFormModal` for today's entry, wait
   for midnight to cross (or `expire_journal` after open), click Save. Modal
   should flip to read-only via 403 catch.
3. **PWA update banner survival**: deploy a new build, refresh — banner shows.
   Click Reload — `pwa:last-reload-attempt` is stamped, post-reload mount
   suppresses re-firing `onNeedRefresh` for 60s. Without this guard, banner
   would re-appear within ms of reload.
4. **Streak freeze at gap**: have a streak of 5, gift a streak-freeze
   consumable, consume it (sets `streak_freeze_expires_at` to today + 1 day),
   skip a day, login on day 7. Streak should be 6, not reset to 1.
5. **Approve all + bulk confirm**: kid with 5 pending approvals across
   chore/homework/creation/exchange/redemption. Parent clicks "Approve all
   (5)" → ConfirmDialog fires (because N > 3) → confirm → fanout via
   `Promise.allSettled` → if one 4xx, others succeed, failure shows error
   chip.
6. **Catalog search after seed**: open Inventory with zero items → no search
   bar visible. Receive any drop → search bar appears. Type "qzqzqz" →
   EmptyState with clear-filter copy (NOT same as zero-items copy).
7. **Boost timer countdown across day boundary**: consume a 24h xp_boost at
   23:55, watch the chip tick over midnight. `xp_boost_expires_at` is a
   timestamp not a counter, so this should "just work" — but the visual
   countdown formatter has bitten us before.
8. **Drop rarity escalation**: 3 drops in quick succession of mixed rarity
   (1 common + 1 rare + 1 legendary). Common goes to `DropToastStack`; rare
   and legendary route to `RareDropReveal` and queue. Verify the queue
   completes serially (legendary doesn't preempt rare).

---

## N. State-gated 4xx paths

Backend rejections that surface as specific user-visible UI.

| Reject reason | Endpoint | Status + body | Frontend behavior |
|---|---|---|---|
| Homework self-plan too soon | `POST /api/homework/{id}/plan/` | `can_plan: false` (gated, no error) | Button hidden when `can_plan=false`. |
| Reward OOS | `POST /api/rewards/{id}/redeem/` | 409 + `similar: [...]` | Suggestion modal w/ similar items. |
| Journal duplicate | `POST /api/chronicle/journal/` | 409 + `existing: <entry>` | Modal flips to edit mode with merged body. |
| Journal locked (PATCH after midnight) | `PATCH /api/chronicle/{id}/journal/` | 403 PermissionDenied | Toast: "that entry is locked now". |
| Streak freeze double-consume | `POST /api/inventory/{id}/use/` | (service-level no-op when already active) | UI silently no-ops. |
| Stack-unsafe consumable N>1 | `POST /api/inventory/{id}/use/ {quantity: 2}` | 400 "can only be used one at a time" | Quantity stepper should clamp at 1 for these. |
| Mount breed cooldown | `POST /api/mounts/breed/` | 400 + days remaining | Hatchery shows per-mount countdown chip. |
| Trophy badge not earned | `POST /api/character/trophy/ {badge_id}` | 400 (server enforces UserBadge ownership) | Picker only shows earned. |

---

## Glossary of force commands (Phase 2)

The companion management commands you'll see referenced above:

```bash
# Force events (write through real services)
python manage.py force_drop --user X --rarity legendary [--slug ITEM]
python manage.py force_celebration --user X --type {streak_milestone|perfect_day|birthday} [--days N]
python manage.py force_savings_complete --user X --goal GOAL_ID
python manage.py force_pet_evolve --user X --pet PET_ID
python manage.py force_notification --user X --type <NotificationType>

# Set state (mutate model fields)
python manage.py set_streak --user X --days 30 [--perfect-days 5]
python manage.py set_pet_happiness --user X --level {happy|bored|stale|away} [--pet PET_ID]
python manage.py set_reward_stock --reward Y --stock 0
python manage.py expire_journal --user X
python manage.py expire_boost --user X --kind {xp|coin|drop|growth}
python manage.py lock_homework_self_plan --user X
python manage.py reset_day_counters --user X

# Tick scheduled tasks
python manage.py tick_perfect_day --user X
python manage.py tick_quest_expire
python manage.py tick_boss_rage
python manage.py tick_chronicle_birthday --user X --as-of YYYY-MM-DD
python manage.py tick_chronicle_chapter --as-of YYYY-MM-DD
python manage.py tick_daily_challenge_rotation
python manage.py tick_habit_decay

# Inventory shaping
python manage.py gift_inventory --user X --slug ITEM --quantity N
python manage.py clear_inventory --user X
python manage.py gift_egg_dupe --user X --species SPECIES_SLUG
python manage.py gift_cosmetic_dupe --user X --slug COSMETIC_SLUG

# Failure injection (cache-flag, auto-clears)
python manage.py inject_failure --queue {chore|homework|redemption|creation|exchange} --status 500 --ttl 60
```

Run `python manage.py <command> --help` for full flag docs.

---

## Notes for future maintainers

- **Keep this in lockstep with new features**. Every PR that adds a celebration
  modal, toast, banner, lock state, or NotificationType should add a row here +
  a corresponding `force_*` command if one doesn't already cover it.
- **The parity test** (`notifications.constants.test.js`) catches new
  NotificationType values that lack frontend meta entries — it does NOT catch
  new visual states. The dev panel + this checklist are the second line of
  defense.
- **Dev panel** lives at `/manage → Test` (parent + DEBUG-gated, see
  `apps/dev_tools/permissions.py` for the gate). Phase 4 of the strategy.
- **Seed scenarios** at `python manage.py seed_test_scenarios` spin up named
  users in pre-baked edge states (`t-streak-99`, `t-locked-journal`, etc.) —
  Phase 3 of the strategy. Until that ships, `seed_data` + the force commands
  here are the manual setup path.
