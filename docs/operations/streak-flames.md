# Private streak flame artwork

The owner supplied four complete SVG documents for the header's streak bonus.
The source artwork, runtime JSON, immutable release files and visual evidence
remain outside Git. Repository code contains only the receiving adapter,
release identity, digest bindings and synthetic test fixtures.

## Candidate and activation hold

| Field | Candidate |
| --- | --- |
| Family | `abby-streak-flames` |
| Version | `1.0.0` |
| Manifest SHA-256 | `e2fb733534ab379e432cbf22dd37d000a264ffab39709179a3dbac2a22609a64` |
| Runtime JSON SHA-256 | `dd285a472e0abcb80d0a87b70dcaf322602808f297bee73da76f4af952d3b435` |
| Runtime JSON bytes | `5253` |
| Status | Private candidate; publication and active application pin pending |

Only `frontend/assets.evaluation.lock.json` records this candidate. The active
`frontend/assets.lock.json` does not adopt it. A private staged directory or an
evaluation pin cannot activate the resolver. Missing, failed, malformed or
unpublished artwork retains an explicit unavailable indicator; it never
substitutes the dormant ember.

Publish the exact immutable release through the existing workshop's authorized
private publisher before adding its pin to the active application lock. The
application's read-only reader cannot publish it. The dedicated legacy avatar
release helper does not cover this file-library family. Do not add an unavailable
family to the production lock, change credentials or delivery settings, or claim
that a local candidate has been delivered.

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

Before activation, verify the candidate's four exact original SVG hashes and
inspect all stages at actual 20/24px on `#FFF8EE` and `#292538`, in grayscale,
and with multiple instances. Check the shared baseline, spark clearance,
reduced motion and actual application stage boundaries. Preserve screenshots
and private verification receipts outside Git. Public CI uses synthetic SVGs
and the explicit unavailable state when private art is absent.

Run the adapter and bonus mapping unit checks, the header/application browser
checks, `npm run assets:verify`, `npm run test:licensed-art`, frontend lint and
coverage, and both web/native builds. Restore the active lock and verified
installed tree after isolated candidate checks. Record exact results and the
publication hold separately from any production delivery claim. Rollback removes
the new active pin and integration while retaining the private immutable
candidate, original art and earlier release pins.
