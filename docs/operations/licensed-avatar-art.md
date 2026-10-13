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
