# React profile and pet implementation record

October 12, 2026. The first R3F slice keeps the complete existing React profile
and pet workflows and adds optional owned-creature presentation. Unity is
[retired](unity-retirement.md). The [roadmap](../superpowers/plans/2026-10-12-r3f-capacitor.md)
still governs production native sessions, integrations and distribution.

## Available behavior

Profile (`/sigil`, alias `/profile`) shows the saved identity, level, trophy and
existing cosmetic controls, plus the server-selected companion. Its links open
account settings, pet care/selection, hatching/breeding, mounts/expeditions and
inventory. Pets (`/bestiary`, alias `/pets`) retain existing server-backed actions.
Meadow uses confirmed active ownership and retains journal capture/receipt
behavior. Legacy Play links stay inside React and drop obsolete token parameters
before authentication, including offline PWA navigation.

The optional view binds exact `chick` / `cute-chick` / `base` to the prepared
Chick; confirmed evolution or an owned mount uses Bird. Growth alone does not
change stage. Unsupported species/variants keep their existing 2D identity.
Greetings award nothing. Lazy loading, failed assets and WebGL loss leave DOM
controls available. Animation is opt-in, pauses in hidden tabs/reduced motion,
and uses demand rendering when idle. Shared geometry/textures are bounded to
the prepared models; cloned skeletons are measured after world-matrix updates.

The [asset boundary](../../content/rpg/react-three-fiber-assets.md) records
private conversion capabilities. Converted Chick/Bird/woodland total 437,440
bytes with embedded textures and verified supplied idle clips. Original sources
are unmodified. Public source builds omit private exports and retain 2D behavior.
Runtime delivery remains private evaluation pending applicable license/seat and
public-packaging assessment; no reusable paid GLB is uploaded by this change.

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

## Private recovery

Generated exports, manifest, hashes and conversion/browser screenshots are saved
outside the managed checkout under the owner's Codex private-assets directory.
The owning chat records the exact location and verifies all four runtime-file
hashes before worktree cleanup. Originals remain in the existing private primary
checkout/backups. No private art is included in the Git recovery snapshot.
