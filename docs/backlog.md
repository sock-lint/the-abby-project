# Backlog

A parking lot for **shaped-but-not-scheduled** ideas — things we've talked through enough to know roughly what they'd look like and why we might do them, but haven't committed to a date.

Anything actively being worked on belongs in [`docs/superpowers/specs/`](superpowers/specs/) (the design) plus [`docs/superpowers/plans/`](superpowers/plans/) (the execution plan), not here. When an entry below graduates, move it out.

Each entry should be self-contained: dated, with enough context that a future reader can pick it up cold, and pointers into the code so the trail isn't cold either.

---

## Interactive canvas moments

**Date raised:** 2026-05-09

### Why it might be worth doing

The RPG layer today is mechanics + ledgers; sprite animations are CSS `steps()` over a sheet (see [`frontend/src/components/rpg/RpgSprite.jsx`](../frontend/src/components/rpg/RpgSprite.jsx)). That's the right primitive for **ambient** feedback — drops, idle pets, growth bars, mount sprites — and it's doing real work in production.

What it can't carry is a **moment** — a 5-second battle hit-reaction when a boss quest takes damage, a pet you can actually pet, a hatching reveal, a perfect-day fanfare, a daily-challenge claim animation. These are the kinds of things that turn a system into a world. They live somewhere between "static UI" and "gameplay" — too rich for CSS+Framer Motion, way too small to justify a game engine.

### Concrete trigger ideas to consider

Each of these is a candidate "first moment":

- **Hatching reveal** launched from [`frontend/src/pages/bestiary/hatchery/Hatchery.jsx`](../frontend/src/pages/bestiary/hatchery/Hatchery.jsx) — cleanest candidate. Already has a dedicated route, a single discrete trigger (`PetService.hatch_pet`), and a natural dismissal point.
- **Pet playground / petting screen** launched from `/bestiary?tab=companions` — could feed `happiness_level` (the field already exists on `UserPetSerializer`, currently only drives sprite dimming via `RpgSprite`'s `dim` prop).
- **Boss-quest hit reaction** when a trigger advances `Quest.current_progress` — a brief flash + damage number above the boss sprite.
- **Perfect-day fanfare** when `evaluate_perfect_day_task` awards a perfect day at 23:55 local — surfaced the next time the child opens the app.
- **Daily-challenge claim animation** on the `/api/challenges/daily/claim/` round-trip.

### Recommended tech path: PixiJS, not a full game engine

**PixiJS is a renderer** — scene graph, ticker, batched WebGL draws — and stops there. **Phaser is a game framework** on top of a renderer (scenes, physics, input, tilemaps, audio). Bundle size: Pixi ~400KB, Phaser ~1MB.

A 5-second hit-reaction or a pet petting screen needs the renderer, not the framework. Concretely:

- Mount one `<canvas>` inside a single React route (or modal), drive from props, unmount on route change.
- Lazy-load via `React.lazy` + dynamic import so the rest of the bundle stays snappy.
- Reuse existing sprite-sheet assets from the Ceph `abby-sprites` bucket — the same data `RpgSprite.jsx` already consumes (catalog at [`apps/rpg/sprite_admin_views.py`](../apps/rpg/sprite_admin_views.py)).
- Wrap the canvas in a `<motion.div>` for entry/exit so it composes with the rest of the journal aesthetic.
- Write the React↔Pixi bridge so Pixi **never owns app state** — props in, lifecycle events (e.g. "animation finished, dismiss") out. Pixi is a leaf, not a co-equal.

Phaser only becomes the right call once we have **gameplay** — a player character moving around a tilemap, collision, enemies. We don't, and probably won't — "kid-spends-time-in-app" is the wrong direction; "real-life-rewards-feeding-into-app" is the right one.

### Why NOT a whole-app engine swap (Unity / Godot / Bevy / Phaser-as-shell)

Would force:

- A separate client (WebGL build or native binary) — losing the single-origin React + Django simplicity that's currently the best thing about the deploy.
- Re-implementing auth, ledgers, and state sync to talk back to Django.
- Trading React Router pages (Dashboard, Yearbook, Manage — where users spend the most time) for in-engine UI, which is dramatically worse for forms, tables, and accessibility.
- Losing Tailwind, Framer Motion, lucide-react, and every accessibility pattern in [`frontend/src/components/README.md`](../frontend/src/components/README.md).

Not on the table.

### What would need to be true before we'd start

A specific moment with a clear trigger and dismissal path that **can't be expressed adequately in CSS + Framer Motion**. Until then, ambient feedback should keep using `RpgSprite` + Framer Motion — the existing primitives are not the bottleneck.

### Pointers for whoever picks this up

- Start with **Pixi v8**.
- Target **one moment end-to-end** before generalizing. The hatching reveal is the recommended first target.
- Read [`docs/superpowers/specs/2026-04-13-rpg-gamification-layer-design.md`](superpowers/specs/2026-04-13-rpg-gamification-layer-design.md) — this entry sits *below* that spec in scope (one moment, not a layer).
- Existing line in the sand for "what CSS can do": [`frontend/src/components/rpg/RpgSprite.jsx`](../frontend/src/components/rpg/RpgSprite.jsx). If a moment needs more than `steps()` over a sheet plus `<motion.div>` composition, that's the threshold for reaching for Pixi.
- Respect the design system's z-stack and modal overlay tokens — see [`frontend/src/components/README.md`](../frontend/src/components/README.md). A canvas moment is still a modal-class affordance.

---

## Functionality review — leftover suggestions

**Date raised:** 2026-05-10

These came out of a focused user-facing-functionality review. Search-on-list-pages shipped with the same review (see [`Projects.jsx`](../frontend/src/pages/Projects.jsx), [`Chores.jsx`](../frontend/src/pages/Chores.jsx), [`Habits.jsx`](../frontend/src/pages/Habits.jsx), [`Trials.jsx`](../frontend/src/pages/Trials.jsx)) — the rest sit here, ranked by leverage. Effort tags: **S** (≤ a day), **M** (a few days), **L** (a week+).

### 1. Re-engagement & reminders

- **Web Push notifications** **[M]** — the PWA stack is otherwise complete ([`frontend/src/pwa/`](../frontend/src/pwa/)) but there's no `pushManager` / VAPID setup. The backend `notify()` call sites in [`apps/notifications/services.py`](../apps/notifications/services.py) already classify by `NotificationType` — wiring push delivery would let every existing notification reach a phone home screen. High-value first targets: `STREAK_MILESTONE`, `CHORE_REJECTED`, `HOMEWORK_REJECTED`, `LOW_REWARD_STOCK`, `REWARD_RESTOCKED`, parent-side `*_SUBMITTED` queue. Pair with a per-type opt-in card on `SettingsPage`.
- **Streak-protect *preventative* warning** **[S]** — today the streak-flame milestones celebrate after the fact. There's no nudge before a streak breaks. [`apps/projects/priority.py`](../apps/projects/priority.py) already has `habit_streak_protection` scoring — extend this into a Celery task at ~19:00 local that emits a `STREAK_AT_RISK` notification (and eventually a push) for any kid with a current streak ≥ 3 who hasn't logged any tracked activity today. Pair with a soft banner on `ChildDashboard` when `now - last_activity > 16h` and streak ≥ 3.
- **"What's new since you last visited" inbox** **[S]** — `ChildDashboard` already loads recent badges + drops, but doesn't *frame* them as "since last visit." Stamp `User.last_seen_at` on dashboard fetch, then on next mount surface a single dismissible scroll: "Since you were here last: 3 badges earned, 1 approval, +12 coins." Cheapest engagement win available — the data is all there.
- **Calendar view** **[M]** — [`frontend/src/api/index.js`](../frontend/src/api/index.js) already exposes `getCalendarSettings` / `updateCalendarSettings` / `triggerCalendarSync`, but there's no UI consumer. A simple month grid on a new `/calendar` route (or a tab inside `/quests`) would surface homework due dates, alternating-week chore schedules, and chronicle birthdays in one place. The backend wiring already exists.

### 2. Insight & analytics (large surface, zero today)

The app currently shows *only* current totals + recent rows. There's no charting library in `package.json` and zero hand-rolled sparklines. Adding even a tiny SVG sparkline primitive would unlock several of these.

- **Coin/earnings sparkline** **[S]** — 30-day sparkline on `ChildDashboard`'s vital pip strip and on [`Payments.jsx`](../frontend/src/pages/Payments.jsx). Backend just needs a `summary_by_day` action on `PaymentLedgerViewSet` and `CoinBalanceView`.
- **Habit strength history** **[S]** — `HabitLog` already records every tap with `streak_at_time`. [`Habits.jsx`](../frontend/src/pages/Habits.jsx) shows only the *current* strength pill — a 14-day mini-bar per habit row would make the decay/regrowth visible.
- **Parent "How is my kid doing" view** **[M]** — [`useParentDashboard.js`](../frontend/src/hooks/useParentDashboard.js) already requests `this_week_by_kid`, but [`apps/projects/dashboard.py`](../apps/projects/dashboard.py) `_parent_extras` doesn't actually return it — that's a latent expectation in the frontend. Land the missing payload (per-child: hours, coins earned, streak, badges this week, pending count) and render a `<KidPulseRow>` card on `ParentDashboard`. Pure-additive backend fix — the UI already has the slot.
- **Skill progression curve** **[S]** — `SkillTreeView`'s backend `get_category_summary()` is computed but never consumed on the frontend. Wire it into the FolioSpread incipit — even just "L2 → L4 in Coding this month" beats the static level chip.
- **Monthly/yearly recap modal** **[M]** — extend `ChronicleService.freeze_recap` into a lightweight monthly recap (auto-generated 1st of month) surfacing top 3 badges, longest streak, coins earned, hours clocked. Render as a one-time `CelebrationModal` variant.

### 3. Onboarding & discovery

- **RPG mechanics tutorial** **[S]** — a new kid lands on `ChildDashboard` and sees coins, levels, vital pips, and drops with no explanation. Add a one-time `WelcomeRPGSheet` (`BottomSheet`) that fires once when `CharacterProfile.created_at` is < 24h: 4 short panels — "Earn coins" → "Level up skills" → "Hatch pets" → "Earn badges." Track dismissal via `CharacterProfile.unlocks` JSONField (already designed for this purpose per CLAUDE.md).
- **Co-parent invite via shareable link** **[M]** — today the founder has to manually type a username + password for the co-parent ([`Manage.jsx`](../frontend/src/pages/Manage.jsx) `FamilySection`). That's friction for the most realistic onboarding path. Add a one-shot `FamilyInvite` token model (24-hour TTL, single-use) + a `/join/<token>` page where the invitee picks their own credentials. Throttled like signup.
- **Empty-state cosmetic upgrade** **[S]** — [`Payments.jsx`](../frontend/src/pages/Payments.jsx) and [`ClockPage.jsx`](../frontend/src/pages/ClockPage.jsx) handle the empty path with a small `RuneBadge` chip. Upgrade to the richer `<EmptyState>` primitive used elsewhere for visual parity. Lorebook is YAML-seeded global content and is always populated, so it doesn't need this.

### 4. Mobile interactions

- **Swipe-to-action on lists** **[M]** — the app is mobile-first but has zero swipe gestures (`onTouchStart` / framer-drag). Highest-leverage targets:
  - Chore rows on `/chores` → swipe-right "complete," swipe-left "skip today"
  - Homework rows on `/quests?tab=study` → swipe-right "submit," swipe-left "needs help"
  - Approval queue rows on `ParentDashboard` → swipe-right approve, swipe-left reject (paired with the existing reject-note `BottomSheet`)
- **Native share for moments** **[S]** — `navigator.share` is unused. Natural emit points: badge earn (`BadgeDetailSheet`), creation approval (`Sketchbook` lightbox), pet evolve (`PetCeremonyModal`). One small `<ShareButton>` primitive in `frontend/src/components/`.
- **Offline read-only caching** **[M]** — [`vite.config.js`](../frontend/vite.config.js) `runtimeCaching: []`. Add a `NetworkFirst` Workbox handler for `/api/dashboard/`, `/api/chores/`, `/api/homework/`, `/api/inventory/` so the app at least *renders* offline (writes still fail loudly, which is correct). Mostly a config change + a small "offline" banner.

### 5. Quality-of-life polish

- **Bulk approve already shipped** for parent dashboard (`Approve all (N)`) — extend the same pattern to the **Manage → Templates** page so a parent can bulk-assign a template to multiple kids in one action. **[S]**
- **Wishlist email** when a wishlisted reward restocks already fan-outs the in-app notification; layer in the existing email backend (`DEFAULT_FROM_EMAIL`) for the same event. **[S]**
- **Inventory "Use × N" stepper** is great — extend it to **Equip multiple cosmetics in one batch** on [`Character.jsx`](../frontend/src/pages/Character.jsx) so kids changing outfits don't round-trip 4 times. **[S]**
- **Quest authoring UX in parent UI** **[M]** — the Trials parent challenge form exists but is sparse compared to the YAML schema. Surface the trigger filter (skill_category, project_id, on_time) as proper pickers rather than the current Advanced JSON-ish panel.
- **Homework "submit due" contextual nudge** **[S]** — make it a contextual nudge on `ChildDashboard` ("📝 Math is due tomorrow, submit it now?") rather than only a quick-actions row.

### Pointers for whoever picks this up

- Pick up the highest-ROI first: **1c (What's new since you last visited)** is the smallest effort with the biggest perceived impact — all the data is already on the dashboard payload, just needs framing + a `User.last_seen_at` stamp.
- Each item is independent — none of them block the others.
- Per CLAUDE.md's "Interaction tests REQUIRED" rule, every clickable element that fires a POST/PATCH/DELETE needs a colocated `*.test.{js,jsx}` interaction test using `spyHandler` from [`frontend/src/test/spy.js`](../frontend/src/test/spy.js).
- The full review document that produced this list is at [`/root/.claude/plans/can-you-review-my-proud-mango.md`](../../.claude/plans/can-you-review-my-proud-mango.md) (outside the repo, on the reviewer's machine).
