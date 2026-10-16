# Catalog icon adoption

Abby catalog icons 1.0.0 adds 160 private, static, transparent 256 × 256 PNGs:
109 item identities, 49 authored challenges and two purchased Chick catalog
portraits. The images total 10,268,866 bytes. This integration does not authorize
production deployment or public publication of workshop assets/evidence.

## Verified delivery

The private delivery index is
`s3://abby-assets-releases/releases/deliveries/abby-catalog-icons/1.0.0/0201085bd500af510bbdbcb16ac3fa68d0588b3cc321a4943d57e64c3cbd4ad2/index.json`.
Its SHA-256 is
`994e77af88d4ac5e3b5b5a536da35bc2d878924b96738768f3acd3e07e7366bf`.
The runtime manifest digest is
`0201085bd500af510bbdbcb16ac3fa68d0588b3cc321a4943d57e64c3cbd4ad2`.

The Abby read-only reader downloaded the index, both handoff files and the
verification workspace ZIP. Each declared SHA-256 and byte count matched before
safe extraction to a new directory outside Git. All 238 workspace inventory
files matched `delivery-files.json`, whose pinned digest is
`7a08d8c1e08b1e8fe7a2d0cb6eba4f88780e440cbb0222bde912db6146b5437c`.
The offline `README-VERIFY.md` command returned `verified:true`, `status:ready`
and the manifest digest above. Workshop readiness is separate from app, staging
and phone acceptance.

The existing code packages already match the exact handoff artifacts:

| Package | Version | SHA-256 |
| --- | --- | --- |
| `@abby-assets/release-tools` | 1.5.0 | `92d40e33741d2609575e8681acc08690c0bc0195ac3e6ee2ca7300415733088b` |
| `@abby-assets/contracts` | 1.3.0 | `b1265f6fbafba348e54d788fb58f8c0e01a913a5ebd3724a1481cc0cf25cd207` |
| `@abby-assets/avatar-runtime` | 1.2.0 | `07e01d1ef5f3003fc2f92bd937e4c008671fd77548df835afbf34c82c7121385` |

Their sizes and npm SHA-512 integrity values also matched. No dependency upgrade
or avatar runtime change is needed. The existing Archer 1.0.2 and Bird Evolution
1.0.0 pins remain unchanged. The merged lock imports 298 files across three
families. All 160 catalog objects were rechecked against the imported manifest
for SHA-256, byte count, PNG signature, dimensions and RGBA encoding.

Follow [shared-avatar-assets.md](shared-avatar-assets.md) for the server-side
reader configuration, `npm ci`, `npm run assets:import` and
`npm run assets:verify`. `frontend/src/avatar/shared/` remains ignored. Credentials
never enter Vite variables or browser requests. Public CI omits private art and
exercises fallbacks; configured required builds fail when imports are absent or
corrupt. Postbuild verification requires every pinned payload in the finished
web/native output. Keep screenshots, handoffs, ZIPs and purchased derivatives
outside Git and hosted CI artifacts. Do not upload them as public sprite art.

## Identity and presentation

`shared/catalog/icon-bindings.json` is code-only identity metadata derived from
the verified private `consumer-bindings.json`. It contains no runtime images,
workshop paths or credentials. Django matches actual catalog records before
returning `catalog_icon` (or `item_catalog_icon` in flattened item responses).
Unrecognized identities retain a null binding and the existing fallback.
Numeric database IDs and legacy sprite keys do not choose images. This keeps
Meat/Chicken Leg, Fish/Cooked Fish and Mega/Treasure Hoard distinct even where
legacy sprite keys are shared.

The sixteen source-inferred consumables retain their provenance flag. Each must
match its slug, expected name and item type on an actual receiving record before
its image is exposed. Local confirmation uses loader-created records in a fresh
disposable database; it does not assert production inventory or grant content.
Missing or mismatched records continue using the previous sprite/emoji.

All 160 bindings matched actual records after loading the application’s authored
catalog into a fresh disposable local database. No mappings were unresolved.
Each of the sixteen consumables was checked individually, including its stored
`metadata.effect`: `streak-freeze`, `scholar-draught`, `lucky-coin`, `drop-charm`,
`growth-tonic`, `rage-breaker`, `scholar-draught-ii`, `lucky-coin-ii`,
`pet-evolution-accelerator`, `feast-platter`, `mystery-box`, `lucky-dip`,
`quest-reroll`, `pet-morale-tonic`, `skill-tonic`, `autumns-gift`.
Their existing visibility/acquisition policy is preserved. Receiving protected
staging records and production records have not been inspected; runtime matching
continues to fail closed for absent or different records in those databases.

`CatalogIcon` resolves only image-kind `icon-256` members from the pinned imported
manifest directory. It renders an ordinary smooth, contained PNG. It does not
call the GLB-only `loadAsset()` helper, apply strip animation, or infer ownership.
Failures are bound to URLs so another item or a refreshed URL remains eligible.
A failed PNG uses the original `RpgSprite` recovery path, including sprite and
emoji fallbacks. The catalog's two Chick portraits are limited to species/grown
catalog thumbnails. Gameplay sprites, creature models, potion/stage presentation,
equipped frame overlays, themes, rewards and authorization remain separate.

## Staging and acceptance

Use [avatar-staging.md](avatar-staging.md) for an isolated, protected staging
application at the reviewed PR head, with a synthetic database and server-side
reader build secrets. Keep automatic/preview deployment disabled. Never retarget
the main-branch production application or copy production data/configuration.
A loopback app browser run with synthetic intercepted APIs and real imported
art establishes local application acceptance only. It does not establish a
finished protected staging deployment, Cloudflare Access, or real-phone use.

Run the repository frontend lint/coverage/web/native checks, relevant Django and
shared API fixture checks, private import verification and required hosted PR
checks. Inspect the actual catalog and shared image surfaces at 32, 40, 64 and
96 CSS pixels on light/dark backgrounds, including selection, failed PNGs,
legacy sprites and emoji recovery. Preserve fallback coverage without private art.

Record the exact staging deployment/health commit and distinct application
identity before phone acceptance. Physical iPhone Safari and Android
browser/WebView checks remain pending; record device/OS/browser, app commit,
manifest digest, small-icon legibility, interrupted image requests, theme changes,
reload and measured performance. Desktop viewport checks do not satisfy them.
Source backup for the new masters also remains pending in the workshop.
Production deployment requires a separate owner request.

## Rollback

The actual application baseline is commit
`87bea6b8272e462edc243be0a27b038a385818aa`: no catalog-icon family pin, the three
code package versions above, Archer 1.0.2 at
`4814589d481fcac4e51a62c7af8e7b4a4e1cf593fde670a281d49480bef09cb3`
and Bird Evolution 1.0.0 at
`1c8bd52e4f2273b1849bebb498d21c0689e7b8d6191c1ee36e7a7bfeb09bd37a`.
Existing catalog, item/challenge and sprite/emoji fallbacks are the presentation
rollback target. There is no earlier workshop icon release to substitute.

Prepare a reviewed revert PR preserving unrelated later work. Restore the asset
lock, identity metadata/API additions and image consumers together, then reimport
and verify the previous two pins and rerun applicable checks. Packages stay at
the baseline versions; this adoption does not change them. No database migration,
restore, reward reversal, inventory deletion or appearance reset is needed.
Keep the immutable private release and evidence for recovery. Merge and production
deployment remain separately gated.
