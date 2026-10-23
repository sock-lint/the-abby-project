# Private streak flame artwork

The owner supplied four complete SVG documents for the header's streak bonus.
The source artwork, runtime JSON, immutable release files and visual evidence
remain outside Git. Repository code contains only the receiving adapter,
release identity, digest bindings and synthetic test fixtures.

## Published application pin

| Field | Release |
| --- | --- |
| Family | `abby-streak-flames` |
| Version | `1.0.0` |
| Manifest SHA-256 | `e2fb733534ab379e432cbf22dd37d000a264ffab39709179a3dbac2a22609a64` |
| Runtime JSON SHA-256 | `dd285a472e0abcb80d0a87b70dcaf322602808f297bee73da76f4af952d3b435` |
| Runtime JSON bytes | `5253` |
| Status | Privately published and independently reader-verified; active application pin adopted |

Abby's existing read-only reader independently fetched the exact remote manifest
and its one runtime object into a fresh import destination on October 22, 2026.
The raw 789-byte manifest matched its pinned SHA-256 and file-library schema;
the 5,253-byte runtime object matched its digest, entry identity and runtime path.
All four embedded SVG documents also matched their original hashes.

Only this verified family moved from `frontend/assets.evaluation.lock.json` into
`frontend/assets.lock.json`. The eleven existing application pins and the
unrelated Crown evaluation candidate retain their exact identities and digests.
The standard release-tools `pin` operation verifies the downloaded release before
adoption; `npm run assets:import` installs the active lock through the ordinary
verified asset pipeline. The application resolver reads only that active lock.

A staged directory or evaluation pin cannot activate the resolver. Missing,
failed or malformed artwork retains an explicit unavailable indicator; it never
substitutes the dormant ember. Private publication and application pin adoption
do not establish a production deployment; the PR still follows ordinary hosted
checks, independent review and merge gates.

## Preparation and receiving contract

The installed contracts and release tools do not accept SVG files directly.
Their existing file-library format accepts reviewed runtime JSON. The private
workspace therefore keeps all four original `.svg` files unchanged and packages
their exact strings in `assets/streak-flames/flames.runtime.json`:

```text
schema_version: 1
view_box: "0 0 24 24"
stages:
  dormant-ember | small-flame | strong-flame | maximum-blaze:
    filename: flame-STAGE.svg
    sha256: SHA-256 of the exact original SVG bytes
    svg: the complete unchanged original document
```

The private file-library recipe has `schema_version: 1`, the family and label,
and one entry with `id: streak-flames`,
`runtime_path: streak/flames.runtime.json`,
`file: assets/streak-flames/flames.runtime.json`, the measured digest and byte
count, and `media_type: application/json`. From `frontend/`, prepare and verify
the candidate with the installed tools and explicit private paths:

```bash
node node_modules/@abby-assets/release-tools/cli.mjs build-file-library \
  --workspace "$FLAME_WORKSPACE" --recipe "$FLAME_RECIPE" \
  --version 1.0.0 --output "$FLAME_RELEASE_ROOT"
node node_modules/@abby-assets/release-tools/cli.mjs verify-release \
  --release "$FLAME_RELEASE_DIRECTORY" \
  --sha256 e2fb733534ab379e432cbf22dd37d000a264ffab39709179a3dbac2a22609a64
```

The result contains `manifest.json` and one content-addressed
`objects/PAYLOAD_SHA256.json` beneath
`abby-streak-flames/1.0.0/MANIFEST_SHA256/`. The ordinary importer verifies the
exact manifest and every payload byte before installing the active pins beneath
the ignored `frontend/src/avatar/shared/` tree. Keep the evaluation tree outside
that application directory until an explicitly isolated private verification.
Never add unmanaged files to an installed tree or rewrite its index by hand.

`streakFlameRelease.js` accepts only the exact active pin, valid file-library
manifest, payload metadata, four stage/filename/digest bindings, original canvas
and a bounded SVG element/attribute allowlist. The importer establishes byte
authenticity; the synchronous resolver does not substitute a browser-written
hash claim for that verification. It reads the JSON and also emits its original
bytes through a Vite URL import. The web/native postbuild gate verifies pinned
JSON alongside the existing PNG and GLB files.

Each SVG renders as a decorative image document with its original gradient IDs.
Separate image documents isolate those IDs when several instances appear. The
complete transparent 24-unit canvas scales uniformly to 20 or 24 CSS pixels;
the silhouettes are neither cropped nor independently resized. The artwork is
static for both ordinary and reduced motion.

## Bonus meaning and validation

`bonusPresentation.js` maps the server-confirmed bonus projection to a stage.
Inactive bonus means dormant ember. Valid active intensity below `0.5` uses the
small flame, intensity from `0.5` to below `1` uses the strong flame, and exactly
`1` uses maximum blaze. Unknown or invalid bonus data has its own unavailable
state. Saved streak counts, personal bests and client day thresholds do not
select artwork. The server normalizes intensity against its actual check-in
multiplier cap; reward calculations and endpoints remain authoritative.

For activation and later changes, verify the four exact original SVG hashes and
inspect all stages at actual 20/24px on `#FFF8EE` and `#292538`, in grayscale,
and with multiple instances. Check the shared baseline, spark clearance,
reduced motion and actual application stage boundaries. Preserve screenshots
and private verification receipts outside Git. Public CI uses synthetic SVGs
and the explicit unavailable state when private art is absent.

Run the adapter and bonus mapping unit checks, the header/application browser
checks, `npm run assets:verify`, `npm run test:licensed-art`, frontend lint and
coverage, and both web/native builds. Preserve the active pin and verified
installed tree after application checks. Any isolated future candidate checks
must restore that active installation afterward. Record exact results separately
from any production delivery claim. Rollback removes the flame active pin and
integration while retaining the private immutable release, original art and
earlier release pins.
