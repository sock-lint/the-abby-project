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
