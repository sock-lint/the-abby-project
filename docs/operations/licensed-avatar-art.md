# Private Profile avatar builds

The Profile preview resolves its Archer model, four hairstyles and supplied
palette textures at Vite build time. The Meadow portrait release stages only
storybook images; it cannot supply the avatar. A build without the separate
avatar inputs displays “The avatar preview is unavailable.”

`Dockerfile` runs `frontend/scripts/stage-avatar-art.mjs` before Vite. Public
builds skip it without an avatar configuration secret. Local purchased assets
are excluded from both Git and Docker contexts. Staging accepts only a reviewed,
bounded runtime release, never original packs, editable sources or credentials
in the browser bundle.

## Owner release prerequisite

The [asset boundary](../../content/rpg/react-three-fiber-assets.md) requires
recorded acceptance of the applicable license, seats and public browser delivery
before publishing converted artwork. This build support does not grant that
acceptance, upload artwork, configure production or establish phone validation.
Generated `private_evaluation` manifests are rejected. An owner-reviewed release
must use `delivery_review: public_runtime_accepted` and a nonempty
`delivery_review_reference` identifying that acceptance record. The marker records
the owner's decision; it cannot itself establish permission.

After that review, the owner can package the verified private Archer export in
the following JSON shape. These placeholders are synthetic, not a release:

```json
{
  "schema_version": 1,
  "manifest": {
    "schema_version": 1,
    "delivery_review": "public_runtime_accepted",
    "delivery_review_reference": "<owner acceptance record>",
    "models": { "archer": { "file": "archer.glb", "idle_clip": null, "rotation_y": 0 } },
    "parts": { "body": "Archer_Body", "head": "Archer_Head", "face": "Archer_Face", "hair": {} },
    "textures": { "outfit": {}, "hair": {}, "face": {} }
  },
  "files": { "archer.glb": { "sha256": "<file digest>", "base64": "<runtime bytes>" } }
}
```

Use the actual complete export manifest, including all four hair names, eight
skin/outfit textures, two hair textures and two face textures. Include exactly
the referenced GLB and PNG files. Limits are 8 MiB for the JSON artifact and
2 MiB for each runtime file, with PNGs bounded to 2048 pixels. The GLB must be
self-contained version 2 with its required mesh parts and no external references
or extensions. Only the accepted static pose is supported; an unaccepted Idle
clip fails validation. Artifact and individual file hashes are verified before
atomic staging. Existing local staging directories are never overwritten.

## Build configuration

The owner must publish the accepted object privately and supply a BuildKit
`ABBY_AVATAR_ASSETS` secret file containing `endpoint`, `bucket`, `key`, `region`,
`accessKeyId` and `secretAccessKey`. This matches the existing Meadow configuration
shape but selects the avatar's immutable object. The endpoint must use HTTPS.
Keep credentials out of Git, build ARGs and command output.

Set `ABBY_AVATAR_ASSETS_SHA256` to the SHA-256 of the complete JSON artifact and
`ABBY_AVATAR_ASSETS_REQUIRED=true` to prevent a production build from silently
omitting the preview. Both values can be supplied as build ARGs or Coolify
build-time secret files. The Dockerfile mounts all three secrets for staging;
the artifact digest is also a nonsecret ARG and should be set as a build ARG
when using direct BuildKit builds so changing releases invalidates the cache.
For Coolify, retain its existing `COOLIFY_BUILD_SECRETS_HASH` integration when
changing a secret-based release. Never rely on secret-content changes alone
to invalidate BuildKit's cache.

A configured release with invalid configuration, a failed download, an absent
digest, unreviewed delivery or missing variants fails the build. Without any
avatar secret and with the required flag false, public CI keeps the existing
functional customization fallback. The final Django image receives only Vite's
compiled output; private credentials remain build secrets.

`npm run test:licensed-art` exercises synthetic staging, public skip/required
behavior, integrity failures and a real Vite build that resolves all 64 avatar
combinations. Hosted Frontend validation runs this gate. Real Archer rendering
and physical-phone acceptance remain owner checks after the approved inputs
are available. Rollback selects a previously accepted object and digest, then
uses the normal reviewed deployment flow.

## Expanded identity and supplied Idle

Saved preferences now include `outfit_style` (`archer-01`, `archer-02`,
`archer-03`) independently from the existing outfit palette. Brown, Orange and
Grey join Light/Dark hair, with matching supplied eyebrow textures across three
face choices (`face-01`, `face-02`, `face-03`, default `face-01`). The code
also supports rounded/pointed ears (`head-01`/`head-02`, default `head-02`),
for 2,880 combinations. This does not establish that a new private release
has been converted, visually accepted or published. Existing static schema-v1
releases remain valid for their original choices; unsupported selections retain
the functional customization fallback.

Schema-v2 manifests use `models` keyed by all three costume identifiers. Each
entry has its own complete `file`, `idle_clip: "Idle"`, and `rotation_y`.
`parts` keeps singular body/face names and four hair names; its `head` map
contains both `head-01` and `head-02`. Each GLB contains all eight modules.
`textures.outfit` has 24 `<style>:<skin>:<palette>` keys,
`textures.hair` contains all five colors, and `textures.face` has 15
`<face_style>:<hair_color>` entries. Reviewed
source-map descriptors may explicitly share palette PNGs between costumes;
the release contains exactly the distinct referenced GLBs/PNGs. The outer
artifact schema remains version 1.

Before public staging, every model must have a nonempty
`animation_review_reference`, the real `animation_source_sha256`, and measured
`animation_validation` from the private converter: `method` is
`supplied-hierarchy-rotation-retarget-v1`; duration is positive and bounded to
60 seconds; at least three frames and one moving vertex were checked.
`source_rest_joint_difference` records the source's different proportions as
a finite nonnegative diagnostic. `target_joint_error`, `rotation_delta_error`
and `head_attachment_error` are at most 0.0001; `nonroot_translation_variation`
and `source_scale_variation` are at most 0.00001; `reimport_max_vertex_error`
is at most 0.001. Joint/translation/vertex metrics are in meters, rotation
uses normalized sign-independent quaternion distance, and scale is unitless.
Target joint offsets are preserved rather than imposing source proportions.
The reference identifies an actual visual review, not a synthetic
test or a converter-generated acceptance. Whole-release license/public-delivery
acceptance still uses the existing owner prerequisite above.

Staging independently checks that each self-contained GLB has only its named
Idle clip, valid skeletal channels/keyframes, a weighted body and real joint
motion. It imports only the renderer contract into the browser manifest;
source hashes, private review references and conversion reports stay private.
The renderer clones each rig, preserves its original weights, and pauses motion
offscreen, in hidden tabs and for reduced motion. Switching costumes loads the
matching complete model; it does not copy animation tracks onto another rig.

Archer 03 requires its original fifth bone influence on one vertex. Exports
retain paired `JOINTS_1`/`WEIGHTS_1` rather than truncating or refitting the art.
The renderer's bounded extra-weight path clones geometry/materials, restores
the loader-normalized first-set share and applies all weights to positions,
normals and CPU bounds/picking. Staging requires paired valid sets, normalized
combined weights and at most eight influences. Geometry and cloned resources
are released with their avatar instance.

Prepare the original pack privately, preserving its directory structure. The
owner-provided inbox on this station is outside Git:
`/home/ubuntu/.local/share/abby-assets/meshtint/female-archer-pack-01/`.
Do not copy purchase records or credentials into the checkout. An inventoried
source-map JSON identifies actual FBX/PSD/PNG/material paths under that pack;
there are no guessed Brown/Orange/Grey face filenames. Run:

```sh
python scripts/r3f/prepare_archer.py --source <private-extracted-pack> \
  --source-map <private-reviewed-inventory.json> --output <empty-ignored-export-dir> \
  --blender <local-blender-executable>
```

Without `--source-map`, the existing static-v1 conversion remains available.
Keep `delivery_review: private_evaluation` until actual artwork and applicable
public delivery have been reviewed. Add `--animation-review-reference` only
for an existing review record after verifying the complete conversion evidence.
Real source reimport/render evidence and physical-phone graphics checks remain
separate from hosted tests, which use synthetic geometry and public fallback.
