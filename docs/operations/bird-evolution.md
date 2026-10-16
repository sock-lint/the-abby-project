# Bird Evolution adoption

Bird Evolution 1.0.0 is a new private shared family, alongside the unchanged
Archer 1.0.2 pin. It replaces the older converted bird presentation when the
shared release is installed. Existing licensed families and 2D fallbacks remain
available. This change does not authorize merging, production deployment or
publication of workshop evidence.

## Exact delivery and verification

The delivery index is at
`s3://abby-assets-releases/releases/deliveries/meshtint-bird-evolution/1.0.0/1c8bd52e4f2273b1849bebb498d21c0689e7b8d6191c1ee36e7a7bfeb09bd37a/index.json`.
Its SHA-256 is
`7a94bfbe1cc03933a04f8f112b039f3001d4107027abf481f34b76c0ba4805b4`.
The pinned runtime manifest SHA-256 is
`1c8bd52e4f2273b1849bebb498d21c0689e7b8d6191c1ee36e7a7bfeb09bd37a`.
Object keys in the index are relative to `releases/`; prepend it exactly once.

On October 16, 2026 the Abby reader freshly downloaded the index, both handoff
files, the verification ZIP and the three code packages. All declared sizes,
SHA-256 hashes and npm SHA-512 integrity values matched. The ZIP was extracted
with hidden directories intact into ignored `scripts/r3f/private/bird-delivery/`.
All 234 workspace inventory files matched the pinned `delivery-files.json`.
The command in `README-VERIFY.md` returned both `verified:true` and
`status:ready`; workshop readiness does not establish app or phone acceptance.
No AbbyAssets workstation files are needed.

| Portable code package | Version | SHA-256 |
| --- | --- | --- |
| `@abby-assets/contracts` | 1.3.0 | `b1265f6fbafba348e54d788fb58f8c0e01a913a5ebd3724a1481cc0cf25cd207` |
| `@abby-assets/avatar-runtime` | 1.2.0 | `07e01d1ef5f3003fc2f92bd937e4c008671fd77548df835afbf34c82c7121385` |
| `@abby-assets/release-tools` | 1.5.0 | `92d40e33741d2609575e8681acc08690c0bc0195ac3e6ee2ca7300415733088b` |

`frontend/package-lock.json` records each declared npm integrity. Only the
code-only tarballs go into `frontend/vendor/`. Runtime models, handoffs, ZIPs,
previews, receipts and source packs remain outside Git. Reader downloads are
GET-only. Never use publisher/backup credentials or copy production secrets.

For a remote import, use the approved `abby-assets-abby-reader` profile in
`~/.aws/credentials` (0600) and `~/.aws/config`, or dedicated server-side
`ABBY_ASSETS_ACCESS_KEY_ID` / `ABBY_ASSETS_SECRET_ACCESS_KEY` secrets. Do not
mix credential providers. Configure the nonsecret endpoint settings from
[shared-avatar-assets.md](shared-avatar-assets.md), then run from `frontend/`:

```sh
AWS_PROFILE=abby-assets-abby-reader \
ABBY_ASSETS_S3_ENDPOINT=https://sfo3.digitaloceanspaces.com \
ABBY_ASSETS_S3_REGION=us-east-1 \
ABBY_ASSETS_S3_BUCKET=abby-assets-releases \
ABBY_ASSETS_S3_PREFIX=releases npm run assets:import
npm run assets:verify
```

The import verifies both exact pins transactionally: Archer's 105 files plus
Bird's 33 files (138 total). Bird's payload is 5,837,748 bytes. Imported trees
remain ignored in `frontend/src/avatar/shared/`. Build-time credentials remain
outside the Vite process and browser bundle. Missing optional private art in
public CI uses the existing fallback; configured required builds must fail on
missing or changed assets.

## Server-owned stages and presentation

The owner selected Fledgling at 50 growth and Bird at the existing 100-growth
evolution threshold. This applies only to the exact supported
`chick` / `cute-chick` / `base` identity. The read-only `evolution_stage` is
derived from persisted growth and confirmed evolution, including already-saved
pets. Mounts use Bird. Other species/potions retain their own presentation.
Existing ownership, family boundaries, food consumption, growth caps, rewards
and mount eligibility remain authoritative in Django.

The release's stable family ID is `meshtint-bird-evolution`; the stage maps to
its `chick`, `fledgling` or `bird` asset with default `source-idle`. Ownership
and stage survive reload through the existing species/potion/growth/evolution
records. Playback choices are temporary presentation, not new inventory or
saved progression. No database migration or reward is needed for Fledgling.

All 31 native motion variants stay on their matching meshes, skins and bind
poses. Each uses its declared loop and source-travel policy. Use the supplied
in-place variants when travel is unwanted; do not retarget tracks or infer a
motion root. The two authored Evolve payloads include their source/destination
rigs and play once. Preload destination idle before transition; completion only
changes presentation. A confirmed direct Chick-to-Bird jump can present both
transitions. Loading errors, newer selections and unmounts cancel stale work
and dispose owned resources. Reduced motion or unavailable 3D keeps the
server-confirmed destination and functional DOM controls.

## Validation and acceptance

Run frontend lint, full coverage, shared-asset verification, web/native builds,
companion playback/loader/component checks and avatar regressions. Run backend
pet growth, feed/consumable, persistence, permissions and contract checks,
including PostgreSQL concurrency checks. Required hosted PR checks remain the
merge gate. Exercise the actual imported models in the consumer browser scene;
synthetic tests and workshop screenshots alone do not establish that result.

Record each acceptance scope independently against the final app commit:

| Scope | Status |
| --- | --- |
| Delivery byte integrity and workshop handoff | Verified as described above |
| Application unit/API/browser and hosted checks | Record exact results in the PR |
| Physical iPhone Safari | Pending; no device acceptance claimed |
| Physical Android browser/WebView | Pending; no device acceptance claimed |
| Signed native distribution and production deployment | Pending owner review |

For each real phone, record device/OS/browser, app commit, release digest and
observations: all stages/motions, both evolutions, paused/background/resume,
slow/interrupted loads, retry, context loss, account change, save/reload,
framing and measured performance/memory. Desktop phone-sized viewports are
separate evidence. Do not mark this checklist passed without hardware use.

## Rollback

The pre-adoption application baseline is commit
`7a681555aba26d81e530d8f6f49708d7f6902226`: Archer 1.0.2 at manifest
`4814589d481fcac4e51a62c7af8e7b4a4e1cf593fde670a281d49480bef09cb3`,
with contracts/runtime/release-tools 1.0.0 and no shared Bird family pin.
The workshop's null previous Bird pin is not an application rollback target.

After an owner-reviewed merge, prepare a new PR reverting the complete adoption
change, preserving unrelated later work. Restore the previous asset/package
locks and renderer/API code together, run `npm ci`, reimport/verify the previous
pins, and repeat the same applicable checks before an owner-approved deployment.
Do not deploy or merge directly as part of this integration task.

No Bird selection or new stage is stored in a new database field; restoring the
old application reads the same existing ownership/growth records and returns to
its Chick/Bird presentation. No database restore, deletion of pets/inventory,
reward reversal or clearing saved Archer preferences is required. Preserve
private evidence and the immutable delivery for diagnosis; never modify a
published release to roll back.
