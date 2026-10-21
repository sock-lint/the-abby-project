# Portrait frame kit integration

The application adds private family `abby-portrait-frame-kit` **1.1.0** as the
tenth release in `frontend/assets.lock.json`. Its exact manifest SHA-256 is
`9c2e4e3c67edc2fa639bd8d92ff27d5929c356b220ccd4868dd2a3550c25bb91`.
The previous nine family pins remain intact. This family supplies portrait
overlays for existing equipped cosmetics; it creates no inventory, ownership,
reward, title, badge, or avatar-selection entitlement.

## Verified private intake

The ready-delivery index is
`s3://abby-assets-releases/releases/deliveries/abby-portrait-frame-kit/1.1.0/9c2e4e3c67edc2fa639bd8d92ff27d5929c356b220ccd4868dd2a3550c25bb91/index.json`.
Its SHA-256 is
`e120092f5b9f2f214f53afab77a4176534c62a221957fc0ce3ce9a6e4a9b1934`.
The index was verified before following its locators. Its object keys are
relative to `releases/`; prepend that prefix once.

| Declared object | Bytes | SHA-256 |
| --- | ---: | --- |
| Handoff JSON | 55,931 | `11e032099584882b04338012cb5470cca0e1f2a47b5a8452b0435d94d70107c9` |
| Handoff Markdown | 16,445 | `63aa7744f66d267a3d9c42a5b9edb1dd2942692c72b53659b1e36a915b10f94b` |
| Runtime review ZIP | 748,086 | `47ba04d02e55498450c809fd3d26128e73e037419cdea7a227a163309768ff4d` |
| Verification workspace ZIP | 2,877,914 | `adbad769a02fc44e741b397298cabead7dee113acd2bd879a303ee7fe2b1651b` |

All four objects matched their declared byte counts and hashes. Archive entries
were checked before extraction outside Git; all **160 inventory files** matched
the extracted verification workspace. The installed release-tools
`verifyHandoff` returned `verified: true`, `status: ready` for the exact family
and manifest digest. Separately, the review bundle's checksums verified all
**71 files**, and `verifyRelease` verified its runtime manifest and objects.

The standard runtime release contains **66 unique transparent PNGs**, totaling
**632,188 bytes**, representing **72 explicit size/density selections**. The
review sidecars are composition references; the standard shared importer stages
only the pinned runtime manifest and content-addressed image objects. Source
masters, review ZIPs, integration sidecars, private previews and receipts remain
outside Git and public CI artifacts.

The delivered code packages match the existing vendor tarballs byte for byte:
contracts 1.4.0, avatar-runtime 1.3.0 and release-tools 1.6.0. Drawing these PNGs
requires no package upgrade. The generic `loadAsset` path is GLB-only; the image
resolver must select this family's pinned image variants instead.

Import through the existing transactional importer and the scoped read-only
reader described in [shared-avatar-assets.md](shared-avatar-assets.md):

```sh
AWS_PROFILE=abby-assets-abby-reader \
ABBY_ASSETS_S3_ENDPOINT=https://sfo3.digitaloceanspaces.com \
ABBY_ASSETS_S3_REGION=us-east-1 \
ABBY_ASSETS_S3_BUCKET=abby-assets-releases \
ABBY_ASSETS_S3_PREFIX=releases npm --prefix frontend run assets:import
npm --prefix frontend run assets:verify
```

The integration's standard read-only import verified **10 pinned releases /
1,758 files**, plus all seven retained supplemental portraits. The synthetic
licensed-art and asset-configuration suites passed **65** and **11** tests,
respectively; no family-count exception or importer change was needed.

Keep dedicated `ABBY_ASSETS_*KEY*` and session-token variables unset when using
this named reader profile. Credentials remain server-side, with no `VITE_`
prefix, source-file entry or browser transport. The existing seven supplemental
companion portraits remain required and separately verified. This kit's
verification workspace contains only its own family and cannot replace the
complete release tree or the roster's supplemental source workspace for a fresh
offline installation. A verified installed supplemental tree may be reused by
the ordinary importer.

## Catalog authority and selection

| Existing catalog slug | Image asset ID |
| --- | --- |
| `frame-laurel` | `item-frame-laurel` |
| `frame-steampunk` | `item-frame-steampunk` |
| `frame-rune-circle` | `item-frame-rune-circle` |
| `frame-cosmic` | `item-frame-cosmic` |
| `frame-scholar` | `item-frame-scholar` |
| `frame-pixel` | `item-frame-pixel` |

The resolver accepts only this pinned family and known asset IDs. Image
availability does not establish catalog identity or ownership. The existing
server-confirmed `active_frame` remains the equipped-slot authority; the
application must not infer acquisition or equip another frame when an image is
missing. Names, initials, titles and earning information remain live DOM text.

| Complete canvas size in CSS pixels | Geometry tier | Explicit densities |
| --- | --- | --- |
| 32, 40 | `small` | 1×, 2×, 3× |
| 64, 96 | `detail` | 1×, 2×, 3× |

Choose density with `ceil(devicePixelRatio)`, clamped to 1–3. The physical image
dimensions equal the selected CSS size times its density. Density never chooses
the geometry tier. Use the separately simplified small artwork for 32/40px;
do not shrink a detailed master to replace it. Other CSS sizes require a layout
review; 36px and 80px have no approved implicit variant.

## Portrait geometry and accessible composition

The authoring canvas is **1024 × 1024**, centered at **(512, 512)**, with a
top-left origin, x increasing right and y increasing down. CSS size refers to
the complete square artwork canvas, including its ornament.

- The nominal circular opening has radius **320** and bounds
  **[192, 192, 832, 832]**, or 62.5% of the complete canvas diameter. Its rim
  has antialiasing; the interior through radius **318** is guaranteed clear.
- The centered circular photo/initial underlay has radius **332**, bounds
  **[180, 180, 844, 844]**, and diameter **664**. In CSS it begins at
  **17.578125%** from the top and left and occupies **64.84375%** of the
  complete width and height. This slight underlap prevents rim gaps.
- Keep face features within the radius-**304** safe circle and conservative
  rectangle **[304, 296, 720, 728]**. Use centered `object-fit: cover`; a
  centered crop does not itself identify the face.
- Outer artwork stays within **[32, 32, 992, 992]**. Keep the outer wrapper's
  overflow visible and clip only the circular portrait underlay.

Overlay images are decorative: empty `alt`, `aria-hidden`, no pointer events.
A missing/failed PNG retains the existing code-native SVG for that same equipped
frame around the readable photo or initial; it never borrows another catalog
item's artwork. A failed photo retains a readable initial. Preserve the existing
identity name, focus ring and
interaction target of at least **44 CSS pixels**, independently of the 32/40px
artwork. A smaller canvas must not shrink its button's hit target.

## Application checks and release limits

Run `assets:import`, `assets:verify`, the resolver/component tests, frontend
lint and coverage, web build and explicit isolated native staging build. The
required hosted frontend/backend/API checks and independent review still apply.
The private Blender companion gate is not an image-family validation substitute.

Inspect actual navigation, Today, Profile and project-signature compositions
with photo and initial states, long names/titles, each size/density, keyboard
focus, enlarged text, light/dark backgrounds, all six Meadow covers and image
failure. Keep browser screenshots and exact-head evidence private. Public CI
uses synthetic inputs and the existing readable fallbacks without private art
credentials.

Verified delivery and desktop browser checks do not establish real-phone
performance or acceptance. **Real-phone acceptance remains pending**, as do
signed native distribution and production rollout unless separately recorded
through their existing release processes. This integration changes no
production settings and performs no deployment.

## Rollback

The application baseline before this family's adoption is commit
`f828410bf6c3483f8663ec4cc64b42e5c9485d7b`, with the previous nine-family
lock and the same vendor packages. The workshop's null previous pin does not
identify an application rollback target.

Prepare a reviewed revert of this family's pin and image adoption while
preserving later unrelated work, then reimport and verify the retained lock and
supplementals. Rerun the applicable tests and release gates. Existing catalog
frame selections remain server-owned and need no data migration: this
presentation does not persist new kit selections or award anything. Never
rewrite the immutable release as a rollback.
