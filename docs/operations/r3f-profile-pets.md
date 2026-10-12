# React profile and pet implementation record

October 12, 2026. The first R3F slice keeps the complete existing React profile
and pet workflows and adds optional owned-creature presentation. Unity is
[retired](unity-retirement.md). The [roadmap](../superpowers/plans/2026-10-12-r3f-capacitor.md)
still governs production native sessions, integrations and distribution.

## Available behavior

Profile (`/sigil`, alias `/profile`) centers the owned Archer avatar, with a
compact saved identity, level and trophy. Basic customization previews four
supplied hairstyles, Light/Dark hair, Fair/Tan skin and Aqua/Nature/Fire/Dark
outfit palettes. Save persists confirmed appearance through the self-scoped
`POST /api/character/avatar/` endpoint. Existing earned cosmetics, trophy,
account settings and profile actions remain available below the avatar.

Pets (`/bestiary`, alias `/pets`) opens the selected or active companion's
woodland automatically. Touching the pet opens its existing care sheet; an
evolved pet leads to its exact owned mount's expedition controls. Food,
activation, hatching, breeding and expedition awards retain their existing
server rules. Purchased icons continue to represent the collection. Views
without matching 3D art retain their own 2D identity and functional controls.
Meadow uses confirmed active ownership and retains journal capture/receipt
behavior. Legacy Play links stay inside React and drop obsolete token parameters
before authentication, including offline PWA navigation.

The optional view binds exact `chick` / `cute-chick` / `base` to the prepared
Chick; confirmed evolution or an owned mount uses Bird. Growth alone does not
change stage. Unsupported species/variants keep their existing 2D identity.
Greetings award nothing. Lazy loading, failed assets and WebGL loss leave DOM
controls available. Pets starts reviewed idle motion automatically, pausing in
hidden/offscreen tabs and for reduced motion. View settings allow 2D presentation
and disabling motion. The scene uses demand rendering when idle. Shared geometry/textures are bounded to
the prepared models; cloned skeletons are measured after world-matrix updates.

The [asset boundary](../../content/rpg/react-three-fiber-assets.md) records
private conversion capabilities. Converted Chick/Bird/woodland total 437,440
bytes with embedded textures and verified supplied idle clips. Original sources
are unmodified. Public source builds omit private exports and retain 2D behavior.
Runtime delivery remains private evaluation pending applicable license/seat and
public-packaging assessment; no reusable paid GLB is uploaded by this change.

The owner accepted the recorded Archer pack for Profile on October 12. Run
`scripts/r3f/prepare_archer.py --source <private Female Archer Pack 01 directory>`
after the owned bird conversion. The private Archer export is 235,276 bytes,
with 298,146 bytes of supplied palette images. Reimport checks verified the
four hairstyles and outfit/skin combinations without changing purchased inputs.
Archer uses a relaxed static pose: the supplied Idle has different bind matrices
and is explicitly unaccepted. No new clothing, fitting or animation is authored.
Migration `0024` adds avatar preferences; appearance changes grant no awards.

## Development native shell

Capacitor Android/iOS source projects use `dist-native` local assets and an
explicit staging HTTPS origin. Native boot skips service workers, web update/
install prompts and browser Web Push setup/teardown. The API client, catalog
pagination and public sprite URLs respect the selected backend. Selected staging
CORS origins can revalidate catalog ETags with `If-None-Match`; no new origin is
allowed by default. Commands and staging CORS setup are in `frontend/CLAUDE.md`.

Both shells were generated and synchronized on Windows. Native signing,
compilation and physical-device installation were not performed: this environment
has no Java/adb or macOS/Xcode capacity. The shell is a development prototype;
legacy token rotation still requires isolated synthetic accounts. Durable native
drafts/device sessions, media/integration parity and store acceptance remain
separate roadmap gates.

## Validation

The October 12 review revision passed 2,960 frontend tests across 294 files and
the coverage gate (88.02% lines, 79.87% branches), lint with existing warnings,
and web build. The affected Django RPG/pet/fixture run passed 481 tests on
disposable SQLite, with its two PostgreSQL-specific tests skipped there.
All 52 avatar/shared-fixture checks, including both concurrency tests, passed
against disposable local PostgreSQL 16; its test container/database were removed.
Local browser checks verified automatic pet/Archer rendering and avatar
customization saving through Django and surviving a reload. The full browser
suite passed all 34 checks with private assets, including the updated profile/
pet scenarios, production-routed offline boot and release replacement. Calendar
geometry waits for the sheet's entrance transform to settle before measuring
the strict 44px touch-target requirement.

Initial prototype validation below remains historical conversion/PWA evidence:

- Full frontend coverage gate: 2,927 tests across 288 files passed; line coverage
  87.79%, branches 79.64%, functions 79.22%, statements 85.41%.
- Frontend lint passed with six existing warnings. Three native configuration
  checks and six synthetic conversion guards passed.
- Seven browser checks passed: phone-width profile/navigation, exact unsupported
  species fallback, real Chick/Bird rendering/animation, actual context loss and
  retry, failed model download and recovery, and no greeting mutations.
- Two production-routed PWA release checks passed, including offline legacy Play
  shell navigation, private API cache isolation and replacement-release updates.
- Web builds passed with private art and without private art. Native staging build
  and Android/iOS sync passed. The optional Three loader emits a large-chunk
  warning; it remains lazy. No production accounts or secrets are bundled.
- 476 affected Django pet/RPG/routing/CORS/shared-response checks passed in
  aggregate. Three existing catalog-drift tests needed Windows UTF-8 mode and
  passed when rerun with `python -X utf8`; SQLite was disposable/in-memory.
  No transaction or reward API schema changed.

Desktop screenshots and GLB reimport evidence validate this prototype's
presentation. They do not establish physical-phone memory, thermal, battery,
accessibility, lifecycle or signed-update readiness. The Phase 0 phone exit gate
remains open.

Interrupted-feed acceptance also remains open: the existing feed endpoint has
no request receipt/idempotency key, and a lost response can leave stale growth
and inventory before another tap. Add receipt-based reconciliation before
claiming safe interrupted feeding or complete native mutation recovery.

## Private recovery

Generated exports, manifest, hashes and conversion/browser screenshots are saved
outside the managed checkout under the owner's Codex private-assets directory.
The owning chat records the exact location and verifies the creature and Archer
runtime-file hashes before worktree cleanup. Originals remain in the existing private primary
checkout/backups. No private art is included in the Git recovery snapshot.
