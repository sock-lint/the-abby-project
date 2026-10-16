# Pedestal and card UI adoption

This adds private family `meshtint-pedestal-card-ui` **1.0.1** alongside the
unchanged Archer 1.0.2, Bird Evolution 1.0.0 and catalog icons 1.0.0 pins.
The runtime manifest is
`abc05d8f7919fc30e19e3c77f2f7f470463666c184c2bdcab70e3778c15f378d`.
The integration was prepared for review and protected staging. The owner later
waived staging and separately requested merging PR #244. Follow the normal hosted
CI, independent review, merge-owner and exact-deployment/live gates; no release
configuration or credential change is part of this integration.

## Verified private delivery

The private index is
`s3://abby-assets-releases/releases/deliveries/meshtint-pedestal-card-ui/1.0.1/abc05d8f7919fc30e19e3c77f2f7f470463666c184c2bdcab70e3778c15f378d/index.json`.
Its SHA-256 is
`ccb67ca29d7e6fbbb0ecf8476f09cf73caf47c11bcc7614f40e548e3f0a468b8`.
Object keys in this index are relative to `releases/`; prepend it once.

On October 16, 2026, the existing Abby reader downloaded and verified the index,
handoff pair, verification ZIP and three code packages directly on abby-01.
Every declared object byte count, SHA-256 and npm SHA-512 integrity matched.
The ZIP was checked for unsafe paths and links before extraction into a fresh
private directory outside Git. All 145 workspace inventory files matched the
hashed `delivery-files.json`. The exact command in `README-VERIFY.md` returned
`verified:true`, `status:ready` and the manifest above.

The delivered contracts 1.3.0, release-tools 1.5.0 and avatar-runtime 1.2.0
tarballs are byte-identical to this app's existing vendor packages. Their pins
and the npm lock remain unchanged. The runtime already supports these native
GLBs and image-kind manifests; no runtime upgrade is needed.

Use the existing server-side reader profile and settings from
[shared-avatar-assets.md](shared-avatar-assets.md):

```sh
AWS_PROFILE=abby-assets-abby-reader \
ABBY_ASSETS_S3_ENDPOINT=https://sfo3.digitaloceanspaces.com \
ABBY_ASSETS_S3_REGION=us-east-1 \
ABBY_ASSETS_S3_BUCKET=abby-assets-releases \
ABBY_ASSETS_S3_PREFIX=releases npm --prefix frontend run assets:import
npm --prefix frontend run assets:verify
```

The transactional importer verifies four releases and 339 runtime files. This
family adds six GLBs and 35 PNGs, **35,246,574 bytes**. All runtime payloads,
handoffs, original packs, derivatives, screenshots and verification receipts
stay outside Git. Source backup for this workshop work remains **pending**;
the portable verification workspace is not an editable source backup.

## Application choices

The existing Hatching screen uses a neutral Normal Egg on the Trunk Pedestal
as decorative artwork when available ingredients exist. It does not depict an
owned species or promise a rarity. Real ingredient names, quantities, eligibility
and hatch actions remain ordinary accessible DOM controls. Only a successful
server hatch response starts the existing completed-hatch ceremony.

The design library's pedestal/card example allows temporary inspection of all
five egg exports, the pedestal alone, the native loops and all 19 UI images.
These are artwork choices, with no inventory, progression, unlock or rarity
mapping. In particular, `HatchingSoon` repeats as anticipation; it cannot
complete a hatch or grant anything. Legendary-looking art is not an entitlement.

Each GLB is independently loaded and hash-checked through the unchanged runtime.
Each native take retains its complete common model root, mesh, skeleton and
AnimationMixer. The scene preserves Y-up metre scale with no axis correction or
per-object height normalization. The pedestal support anchor is
`[0, 2.028465509414673, 0]`; an egg's common root is placed there with an
intentional 0.002 m gap. Apply any future scene placement/scale to the whole
composition, and verify full-motion clearance again before adding other objects.
Visibility, background and reduced-motion gates pause playback; disposal and
aborted selection cancel owned loads. WebGL/asset failures retain DOM fallbacks
and hatch controls.

PNG rendering resolves actual manifest object paths and defaults to the 512px
web variants. The 16 native 1024px variants require an explicit review choice;
the three web-only images retain their 512px source. Full square canvases and
transparent margins remain proportional. Emblems are already part of the card
faces; live content is beside the art. No blank card slot, rating system or
nine-slice border is inferred. The frame example uses the guide's measured
common presentation opening with intentional padding, preserving the source's
very low alpha noise. Image failure restores an accessible fallback.

## Validation and staging

Run frontend lint and full coverage, asset verification, web and explicit native
staging builds, and the required hosted PR checks. Run the private current-app
browser checks with imported assets; workshop Lab results retain source drift
and cannot establish current-app acceptance. The browser fixture uses synthetic
local accounts and API responses. Keep screenshots outside Git and public CI
artifacts. Record the exact tested commit and results in the PR.

Follow [avatar-staging.md](avatar-staging.md) for an actual protected deployment:
use the separate staging application, preserve its synthetic database and saved
choices, pin the reviewed branch/commit, keep automatic and preview deployment
disabled, and verify Access across health, API and asset paths plus direct-origin
denial. Reader credentials remain build-time only. Ordinary Vite build output
contains paid files; build secrets and app login alone do not protect those
static URLs. Do not send the bundle to production or public preview hosting.

Physical iPhone Safari, Android browser/WebView and signed native installation
checks remain pending. Record actual device/OS/browser, app commit and release
digest; inspect all loops, full-motion clearance, framing, proportional PNGs,
transparent edges, readable text, keyboard/touch access, slow/failing loads,
pause/background/resume and measured memory/performance. Desktop phone-sized
viewports and software GPU rendering do not satisfy device acceptance.

The six retained `NODE_SKINNED_MESH_NON_ROOT` advisories have no validator
errors; preserve the common native hierarchy. Unity particles, shaders,
AnimatorControllers, demo UI wiring, postprocessing and skybox remain outside
this adaptation. No Unity parity is claimed.

## Actual rollback baseline

The pre-integration application baseline is
`46831052ecb3966ee7178b52090898dcd88b7c84` (the current main integration baseline).
It pins Archer 1.0.2 at
`4814589d481fcac4e51a62c7af8e7b4a4e1cf593fde670a281d49480bef09cb3`,
Bird Evolution 1.0.0 at
`1c8bd52e4f2273b1849bebb498d21c0689e7b8d6191c1ee36e7a7bfeb09bd37a`
and catalog icons 1.0.0 at
`0201085bd500af510bbdbcb16ac3fa68d0588b3cc321a4943d57e64c3cbd4ad2`,
with contracts 1.3.0, release-tools 1.5.0 and avatar-runtime 1.2.0. Private
baseline records retain this integration baseline and the original implementation
baseline `f93bf97b069c45797e22a6356e8da05de8461449`, including their asset and
package locks. A null previous workshop pin is not the app's rollback baseline.

To roll back after a separately authorized rollout, prepare a new reviewed PR
reverting this integration together with its pedestal/card family pin, preserving
later unrelated work. Reimport and verify the retained three releases and rerun the
applicable checks and protected staging acceptance before any deployment. No
database migration, inventory/reward reversal or saved-avatar reset is needed.
Never rewrite an immutable workshop release to perform a rollback.
