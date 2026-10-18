# Achievement card kit integration

The application pins private family `abby-achievement-card-kit` **1.0.0** at
manifest SHA-256
`04f482b958aa1bf9b7f63911339eeeba59ae5745008b6355d71daf7e93e2c8c3`.
The six existing family pins, portable code packages, and exact catalog artwork
bindings remain unchanged. This integration adds presentation, not a new badge,
earning rule, inventory item, cosmetic entitlement, or saved selection.

## Verified private intake

The digest-pinned index is
`s3://abby-assets-releases/releases/deliveries/abby-achievement-card-kit/1.0.0/04f482b958aa1bf9b7f63911339eeeba59ae5745008b6355d71daf7e93e2c8c3/index.json`.
Its SHA-256 is
`e0017075e81af7a2e22c67ea818c73246db8cc2e7c149d3ae1c23b33ac7d4276`.
Declared object keys are relative to `releases/`; prepend that prefix once.

The configured Abby read-only reader verified the index before using its
locators, then checked the byte count and SHA-256 of all three declared downloads:
`handoff.json`, `handoff.md`, and the verification workspace ZIP. ZIP entries
were checked for absolute/traversing paths, duplicates, symbolic links, and
bounded uncompressed size before extraction outside Git. All **89 inventory
files**, plus the inventory itself, matched the extracted workspace exactly.
The installed release-tools verifier returned `verified: true`, `status: ready`
for the handoff and pinned runtime manifest. All three delivered code tarballs
are byte-identical to the existing vendor packages and match their SHA-512
integrities; no package upgrade is needed.

The release contains seven runtime PNGs, **884,341 bytes** in total. Private
artwork, delivery files, handoff references, previews, screenshots, and receipts
stay outside Git. Editable source masters are excluded from this delivery; the
workshop reports source backup as pending, not verified off-machine backup.

Import through the existing transactional importer described in
[shared-avatar-assets.md](shared-avatar-assets.md):

```sh
AWS_PROFILE=abby-assets-abby-reader \
ABBY_ASSETS_S3_ENDPOINT=https://sfo3.digitaloceanspaces.com \
ABBY_ASSETS_S3_REGION=us-east-1 \
ABBY_ASSETS_S3_BUCKET=abby-assets-releases \
ABBY_ASSETS_S3_PREFIX=releases npm --prefix frontend run assets:import
npm --prefix frontend run assets:verify
```

This preserves all installed pins and the seven retained supplemental companion
portraits. A fresh offline import still needs the complete release tree and the
pinned companion verification workspace; this kit's workspace contains only its
own release. Credentials remain server-side and read-only. This PR changes no
production settings and performs no deployment.

## Image contract and composition

`src/avatar/achievementCardKit.js` selects only this family's pinned manifest
and known image IDs. It resolves Vite image URLs for web and native builds;
`loadAsset` is GLB-only and the older `resolvePedestalImage` assumes other
variants and square sizes. Neither loader is used for this kit.

| Asset IDs | Variant | Native dimensions |
| --- | --- | --- |
| `abby-card-base-wide`, `abby-card-border-gold-wide` | `wide` | 1024 × 512 |
| `abby-card-base-tall`, `abby-card-border-gold-tall` | `tall` | 1024 × 1280 |
| `abby-icon-book`, `abby-icon-heart`, `abby-icon-compass` | `icon-512` | 512 × 512 |

Pair bases and overlays with the same shape. Preserve the 64px source corner
slices and scale the 96px content-safe insets using the same card-width scale.
Cards can grow vertically around live content without distorting their corners.
The source outer radius is 48px; the gold overlay is 24px thick. The icon canvases
retain 64px transparent margins on all sides. Real alpha remains intact; guides
are metadata only and never rendered as part of a card.

Wide cards serve compact featured Profile achievements. Tall cards serve earned
badge collections, challenge cards, and reward offers. Live DOM content supplies
names, rarity, progress, prices, and controls. Existing badge/catalog artwork
keeps its exact identity; the three generic icons have no automatic assignment
to a badge, catalog item, earning path, or rarity. The surrounding Meadow design
system remains responsible for typography, controls, focus, and spacing.
Missing or failed private images retain the readable ordinary card and its
controls.

## Acceptance and release limits

Run the focused resolver/component checks, full frontend lint and coverage,
`assets:verify`, web and explicit isolated native builds, and the hosted PR
validation checks. Verify private browser layouts at phone and desktop widths,
long and enlarged text, light/dark backgrounds, and each icon at 24/32/40/64/96
CSS pixels. Keep private PNG screenshots and receipts outside Git and public
CI artifacts. Record the exact tested application head and results in the PR.
Public CI has no artwork credentials and exercises labelled fallbacks.

Workshop acceptance proves delivery integrity and source artwork acceptance,
not current-app composition or physical phone performance. Desktop browser
viewports and native builds do not establish signed native distribution or real
phone acceptance. Production deployment remains with the normal application
release process after the repository's hosted CI and independent review gates.

## Rollback

The pre-integration baseline is application commit
`05b23c6658ec2ce04fa292d94e6733124932effb` on `main`, with the existing six-family `assets.lock.json`, contracts
1.3.0, avatar-runtime 1.2.0, and release-tools 1.5.0. The kit is newly introduced;
a null workshop previous pin is not an application rollback target.

Prepare a reviewed revert of this integration, including its family pin and UI
adoption, while preserving later unrelated changes. Reimport and verify the
retained six-family lock and unchanged supplemental portraits, then rerun
applicable frontend and hosted checks before the normal application release.
No database, reward, inventory, or saved-selection migration is required: this
integration persists no kit selections and grants nothing. Never rewrite the
immutable release as a rollback.
