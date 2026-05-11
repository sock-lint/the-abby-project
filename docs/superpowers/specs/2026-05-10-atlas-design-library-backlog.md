# Atlas Design Library — Backlog

Companion to PR #105 (the five-phase consolidation that lifted `IlluminatedVersal`, `BadgeSigil`, `IncipitBand`, `ChapterRubric`, `RarityStrand`, and `mastery.constants` to `components/atlas/` and applied the vocabulary to Bestiary, Projects, Yearbook, and the Dashboard hero).

These items were deliberately deferred during the consolidation pass. They are tractable, but each one is independent enough to ship on its own — none are blockers for the merged PR.

## Code de-duplication

### Consolidate `RARITY_KEYS` / `RARITY_ORDER` definitions

`RARITY_KEYS` and `RARITY_ORDER` now live canonically in [`components/atlas/mastery.constants.js`](../../../frontend/src/components/atlas/mastery.constants.js), but four page-scoped files still define their own local copies of the same literals:

- [`pages/achievements/collections.constants.js:7-9`](../../../frontend/src/pages/achievements/collections.constants.js)
- [`pages/character/character.constants.js:46-47`](../../../frontend/src/pages/character/character.constants.js) (also re-exports `RARITY_KEYS` at line 141)
- [`pages/bestiary/party/party.constants.js:21`](../../../frontend/src/pages/bestiary/party/party.constants.js) (`RARITY_ORDER` only)
- [`pages/manage/CodexSection.jsx:26`](../../../frontend/src/pages/manage/CodexSection.jsx) (`RARITY_ORDER` only)

The duplicates are identical literals today, so behavior is unaffected — but any future change to the rarity vocabulary (a new tier, reordering, etc.) would require touching all four. Replace each local definition with `import { RARITY_KEYS, RARITY_ORDER } from '../../components/atlas/mastery.constants'`. Mechanical edit; one PR, one commit.

## Visual / UX follow-ups

### Apply the atlas vocabulary to additional surfaces (selective)

Pages explicitly **out of scope** per the original audit (utilitarian working interfaces — Manage, Settings, Payments, Timecards, ClockPage) should generally stay plain, but a few have natural seams that wouldn't cross the "over-decorate" line:

- **Payments page** — wage-week section headers could carry `chapterMark(idx)` numerals (§I Week of Apr 7 / §II Week of Apr 14). Read-only ledger rows stay plain.
- **Settings — Theme picker section** — each cover swatch is already semi-ornate; the selected theme could gain a `RARITY_HALO`-style ring (using `gold-leaf` for the active selection rather than a rarity tier).
- **Manage — Children list rows** — a small `IlluminatedVersal` of each child's display-name initial would echo `<AvatarMenu>`'s fallback initial pattern with more typographic weight. Skip for parents/co-parents — those rows shouldn't be visually-equivalent to children.

These are each ~30-line PRs. Do not bundle.

### `HeroPrimaryCard` idle + parent variants

Phase E deliberately left the `idle` and parent variants without a versal because their copy is generic ("Nothing pressing — pick something." / "{count} things need your seal today"). Revisit only if the inconsistency reads as a gap rather than a deliberate quiet — the gentle-nudge doctrine generally prefers "quiet" over "anchored." If we do add versals, a sensible mapping is:

- **`idle`**: letter from the day's weekday initial (M/T/W/T/F/S/S), fill = 0% (locked tier), no halo. Reads as "fresh page, nothing inked yet."
- **Parent (count > 0)**: letter = first digit of the count? Or "P" for pending. Fill = `(count / 10) × 100` capped. The single-digit-as-letter path is novel and worth user-testing before committing.
- **Parent (idle)**: letter "N" (Nothing) at gilded tier, fully gilt. Reads as "all sealed."

### Companions / Mounts active-card semantics

The active-pet/active-mount card currently carries `ring-2 ring-moss` (Companions) and `ring-2 ring-gold-leaf` (Mounts) on the outer `ParchmentCard`, with the rarity halo on the inner sprite container. The two rings can read as competing accents on a rare-tier active mount. Two paths:

1. Move the active-state indicator from the card border to a small "active" chip on the sprite container (consistent with the existing `<Star size={10} /> active` script line below the name). Drops the ring conflict entirely.
2. Promote the rarity halo to the card outer (replacing the active-state ring) and use a foil sheen for active. Bigger visual change.

Path 1 is the lower-risk move. Confirm with the design intent before touching.

### Yearbook past-chapter "current chapter" hint

Past-chapter `ChapterCard` variants use a small `<IlluminatedVersal>` at gilded tier (`progressPct={100}`). If a chapter ended with a graduation milestone, that gilding reads as "honored"; for a chapter that was abandoned mid-year (e.g. legacy data), gilded reads as overclaiming. A simple fix: pass `progressPct` derived from `stats?.entries_count` or a similar count proxy rather than hardcoded 100. Skip unless we actually see abandoned-chapter rows in the wild.

### `prefers-reduced-motion` visual audit

The cohort's CSS animations (`halo-rise`, `gilded-glint`, `versal-gilt` transitions) all sit inside the existing `@media (prefers-reduced-motion: reduce)` block in [`index.css`](../../../frontend/src/index.css). The PR description includes this in the test plan but it was never verified by an actual reduced-motion render. Verify in a browser with the OS-level reduced-motion preference enabled — confirm the cohort lands as still images on Skills, Badges, Character, Bestiary, Projects, Yearbook, and Dashboard.

## Testing follow-ups

### Smoke tests for the apply phases that didn't get explicit coverage

The five apply commits each landed with at least one targeted test (most often pinning a `data-tier` / `data-progress` / `data-rarity` attribute or a class-string match), but a handful of variants are still only covered transitively through existing tests:

- **`pages/bestiary/party/Mounts.test.jsx`** — has no equivalent to the Companions "wraps each pet sprite with a rarity-keyed atlas halo" assertion. Mirror the Companions test against the mounts fixture.
- **`pages/bestiary/hatchery/Hatchery.test.jsx`** — does not assert that `§I` / `§II` numerals render in the section headers. Add a single `expect(screen.getByText('§I')).toBeInTheDocument()` per phase.
- **`pages/bestiary/codex/BestiaryCodex.test.jsx`** — owned-mount tile rarity halo (the Phase B swap from `ring-gold-leaf` to `RARITY_HALO[potion.rarity]`) is uncovered. One assertion that an owned legendary tile carries `ring-gold-leaf` AND a common tile carries `ring-moss` would pin the rarity-aware halo.
- **`pages/project/PlanTab.test.jsx`** — milestone numeral prefix is uncovered. Add `expect(screen.getByText('§I')).toBeInTheDocument()` to the existing "renders milestones" test.
- **`pages/yearbook/ChapterCard.test.jsx`** — current-chapter IncipitBand renders, but the test only asserts the title shows. Add an explicit `container.querySelector('[data-versal="true"]')` assertion for the embedded versal, and confirm the past-chapter variant carries a versal at `data-tier="gilded"`.

Each addition is 3-6 lines of new test code; the page-level renders already happen.

### Coverage threshold sanity check

Phase A's mechanical move + the apply phases together added ~11 new tests. The vitest gate (65/55/55/65) is currently passing comfortably. After the de-duplication / additional apply work above lands, re-run `npm run test:coverage` and confirm we're not within 1-2% of the threshold on any axis — that's the early-warning signal that a future patch could trip it.

## Documentation follow-ups

### Storybook / `__design.jsx` entries for the atlas cohort

`pages/__design.jsx` is the playground for primitive auditing. It currently imports `IlluminatedVersal` and uses it in a couple of demo blocks. Add explicit demo sections for each lifted primitive:

- `BadgeSigil` in all five rarities × earned/unearned states × with/without `hint`
- `IncipitBand` in three modes: with rarity strand (Reliquary), without (Yearbook), and bare (no kicker, no meta)
- `ChapterRubric` with both API forms (direct `name`/`icon` and legacy `subject`) and with/without `summary`
- `RarityStrand` at compact + default heights, with full counts and empty counts

This is the canonical reference for parents/contributors trying to build a new surface — putting the primitives in one rendered page is more useful than the README's prose.

### Migration note in `components/README.md`

The README's "Atlas cohort" section documents the current API but doesn't carry a migration note for anyone who has external code (a fork, a plugin, a downstream consumer) importing from the old `pages/achievements/` paths. Add a short "Imported from `pages/achievements/...`? Move to `components/atlas/...`" callout above the API table.

---

## Out-of-scope, listed for completeness

These came up during the audit but are bigger than a follow-up PR and likely need their own design review:

- **Lift `TomeShelf` / `TomeSpine` / `FolioSpread` / `SkillVerse` / `CollectionFolio` from `pages/achievements/`** — currently 1 consumer each (Skills or Badges). The "promote on 2nd consumer" rule says: don't move until a third surface (Bestiary, Lorebook, …) wants the folio-spread layout. Re-evaluate if a future page proposes a two-page parchment spread.
- **A `<DebossedTile>` primitive** — `BadgeSigil`'s unearned variant, the Codex's locked-mount tile, and the Sigil Frontispiece's locked cosmetics all share a "pressed intaglio" shadow vocabulary that could become a single primitive. Currently each surface re-declares the same `shadow-[inset_0_2px_6px_-2px_rgba(...)]` literal. Worth doing once a 4th surface needs it; the visual is too specific to abstract speculatively.
- **Atlas vocabulary on RPG-domain components** — `RpgSprite` could potentially wrap itself in a `RARITY_HALO` ring when given a `rarity` prop, removing the need for callers (Companions / Mounts / Codex / Inventory) to wire the halo div themselves. Bigger refactor; only worth it if 5+ call sites converge on the same wrapper shape.
