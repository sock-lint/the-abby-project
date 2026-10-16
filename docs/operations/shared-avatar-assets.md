# Shared avatar assets

AbbyAssets is the authoring and release workshop shared with workQuest. This
client pins Archer **1.0.2** in `frontend/assets.lock.json`, including the exact
manifest SHA-256. Appearance assembly, fitted equipment, resource ownership and
animation playback come from `@abby-assets/avatar-runtime`. React, Three.js and
React Three Fiber remain this application's dependencies.

Bird Evolution 1.0.0 is pinned alongside Archer; its delivery, code-package upgrade,
server stages and rollback are documented in [bird-evolution.md](bird-evolution.md).

## Install and update

From `frontend/`, install the checked-in, code-only package tarballs with `npm ci`.
Then select a private release source and run:

```powershell
$env:ABBY_ASSETS_RELEASE_ROOT = 'PATH_TO_ABBYASSETS/.local/releases'
npm run assets:import
npm run assets:verify
npm run dev
```

The importer verifies every byte and an exact allowlist of files before swapping
the dedicated `frontend/src/avatar/shared/` tree. This directory and interrupted
staging trees are ignored by Git and Docker. Never add the purchased runtime
payload, source archives, Blender files or authoring manifests to the repository.
Verified local installs need no workshop path or remote credentials to build.
Stop Vite before updating assets if a Windows watcher holds the directory open.

For an upgrade, review the new release, copy its pin into `assets.lock.json`, import,
run the frontend checks and inspect the Profile scene. A rollback restores the
previous lock and imports it again. Releases are immutable; never rewrite a
published version. Saved choice IDs need an explicit migration before removal.

Portable source packages live in `frontend/vendor/`; npm's lock records their
integrity. Publish subsequent code changes under new package versions and update
both consumers. Neither consumer runs Blender during install or build.

## Private Spaces builds

The recommended shared storage is one private runtime bucket and a separate
private source-backup bucket. This app receives read-only access to the runtime
bucket through its build environment. It never receives source-backup access.

Omit `ABBY_ASSETS_RELEASE_ROOT` and configure the following server-side variables
or the same-named Docker BuildKit secrets:

```text
ABBY_ASSETS_S3_ENDPOINT=https://sfo3.digitaloceanspaces.com
ABBY_ASSETS_S3_REGION=us-east-1
ABBY_ASSETS_S3_BUCKET=abby-assets-releases
ABBY_ASSETS_S3_PREFIX=releases
ABBY_ASSETS_ACCESS_KEY_ID=<read-only shared-release build secret>
ABBY_ASSETS_SECRET_ACCESS_KEY=<matching secret>
ABBY_SHARED_ASSETS_REQUIRED=true
```

Do not use a `VITE_` prefix or put credentials in source, lockfiles or command
arguments. `ABBY_ASSETS_SESSION_TOKEN` is supported when a temporary credential
provider needs it; omit it for the static Spaces key pair. These dedicated names
are mapped to the SDK's AWS variables only inside the shared-assets process.
Existing `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` secrets used by media or
older art staging remain unchanged. A dedicated shared pair also clears an
inherited AWS profile and stale token for this process so the intended reader
key is used. Partial or blank dedicated credentials fail without printing values.
The Docker build stages the shared release through secret mounts before Vite.
It also copies the portable vendor packages before `npm ci`. Existing licensed
art staging remains available for older deployments.

For these URL-safe settings, leave Coolify's literal-value option disabled.
Coolify 4.1.2 otherwise preserves enclosing quotes in BuildKit secret values;
the importer deliberately rejects a quoted `true` rather than changing secret
bytes. Keep the seven settings build-time only, with runtime and preview access
disabled.

For local named profiles, leave all `ABBY_ASSETS_*KEY*` / `ABBY_ASSETS_SESSION_TOKEN`
variables unset and select `AWS_PROFILE=abby-assets-abby-reader`. Use either a
profile or exported AWS credentials, avoiding mixed credential sources.

Public CI can build without either private avatar release and keeps the labelled
fallback. Any staged shared tree must verify, even when assets are optional.
Set `ABBY_SHARED_ASSETS_REQUIRED=true` for deployments intended to include Archer;
missing or corrupt private inputs then fail the build. Do not change this setting
to suppress a delivery failure. The release has passed live Spaces publication
and readback. Abby's named reader profile freshly downloaded all 105 files and
verified the pinned manifest and exact inventory.

On 14 October 2026, the seven settings above were saved and read back on the
canonical Coolify application `lr5dn6lhga31vyk6u5qvhm4c`. They are build-time only,
with runtime and preview access disabled; both credential fields are locked in
the UI. The existing Docker Build Secrets setting was verified enabled before
and after configuration. The key comes from the dedicated Abby read-only reader,
with no publisher or backup access. GitHub's public validation image does not
receive these secrets. No deployment was requested; the integrated source must
be committed and pushed before a hosted build can use it.

Force a build without cache after changing or revoking build credentials or
storage settings. Docker secret contents do not invalidate cached layers, and
Coolify 4.1.2 does not pass its secret hash as a build argument in secret mode.
An asset lockfile change already invalidates the shared import layer.

## Application behavior

`sharedRelease.js` maps the existing server-confirmed appearance preferences to
portable shared IDs and resolves Vite's URLs for web `/static/` and native builds.
Django's saved avatar configuration, choice validation, ownership, rewards and
unlocks remain authoritative. No API or database changes are needed for this
release. Configuration IDs contain no workstation path or release URL.

The Profile scene retains its camera, lighting, 1.65 m display framing, orbit
controls, loading/error/retry behavior and hidden/offscreen/reduced-motion gates.
The shared instance owns its parsed resources and skeleton. Hop plays skeletal
Jump once, then returns to Idle; Bow and Twirl retain the product's reactions.
All nine clips are available through the shared runtime; this does not add new
gameplay actions or unlocks. The prior licensed renderer remains a fallback for
checkouts without the shared release.

`predev`, `prebuild`, `prebuild:native` and `prepreview` verify the installed tree.
Web/native postbuild checks hash every pinned GLB/PNG in the finished output.
The runtime checks each fetched model/texture's size and SHA-256 before assembly.
Vite retains shared media as files so verification does not depend on inlined
data URLs. This release stages the full 105-file family, **93,088,255 bytes**;
the browser loads the selected model/modules/equipment on demand.

## Verification and limits

Run the normal lint, Vitest and web/native build checks, plus
`npm run assets:verify`. Native builds still require the explicit isolated staging
configuration described in `frontend/CLAUDE.md`. A desktop build is not a device
performance or native lifecycle acceptance test.

The workshop tested both renderer profiles and the actual Profile scene, including
three bodies, combined equipment, skeletal Jump, pause/remount and corrupt-file
handling. The 99 exact release GLBs passed Khronos validation with zero errors
and 132 warnings (PNG features and skinned mesh parents); those warnings remain
recorded in the private workshop evidence. Live private Spaces transport and a
complete source-backup restoration/rebuild drill passed. Real phones and signed
native releases remain pending.

Production promotion and rollback use the separate
[shared avatar production handoff](shared-avatar-production.md). That runbook
does not authorize a merge, public delivery or deployment.
