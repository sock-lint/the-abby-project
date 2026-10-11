# Private Meadow portrait builds

Public Git contains presentation code and a release pointer, never purchased
portraits, pack archives, or storage credentials. `.dockerignore` excludes both
licensed staging directories from every Docker context. Unity has its own
separate private build/deployment process.

The frontend build downloads one private S3-compatible object using the
official AWS SDK, verifies its SHA-256 digest, validates its presentation and
bounded PNG data, and stages the portraits for Vite. The final application
serves the portraits it uses; raw pack archives and private storage credentials
are not shipped to browsers or the final Django image.

## Coolify

Enable `use_build_secrets` for the existing application. Reuse its existing
build-time `AWS_S3_ENDPOINT_URL`, `AWS_STORAGE_BUCKET_NAME`,
`AWS_S3_REGION_NAME`, `AWS_ACCESS_KEY_ID`, and `AWS_SECRET_ACCESS_KEY` settings.
Add build-time `ABBY_MEADOW_ASSETS_REQUIRED=true` for production. The Dockerfile
explicitly mounts these files under `/run/secrets` for staging only.

`frontend/scripts/meadow-art.release.json` contains the object key and digest.
It contains no artwork or credentials. Updating this tracked file selects a
verified new object and invalidates the Docker staging layer without depending
on whether Coolify transports build variables as ARGs or secrets.
`COOLIFY_BUILD_SECRETS_HASH` is declared for compatibility with Coolify's
Dockerfile handling; the tracked release pointer supplies the artwork cache key.
Keep the staging RUN and `npm run build` RUN
separate: Coolify injects existing Sentry/VITE secrets into the latter.

Only `django` declares the shared application image's Compose build. The Celery
worker, beat and printer listener use the same image tag. Coolify 4.1.2 accumulates
Dockerfile output when rewriting the same Dockerfile for multiple services with
build secrets enabled, eventually failing with `Argument list too long`. Building
once avoids that failure. Coolify builds before starting services, and a full
local `docker compose up --build` builds the shared image too. On a fresh checkout,
run `docker compose build django` before starting an individual worker service.

Upload each immutable release object privately before updating the pointer.
The JSON artifact has this shape (the example is synthetic):

```json
{
  "schema_version": 1,
  "presentation": { "schema_version": 1, "palette": {}, "typography": {}, "companion": {}, "keepsakes": [] },
  "images": { "chick.png": { "sha256": "<image digest>", "base64": "<PNG bytes>" } }
}
```

Use the current privately staged presentation. Its palette, typography,
keepsakes, schema version and companion ID must match the public contract;
the companion label, art key and portraits may change. Each referenced
portrait must be in the bundle. Limits: 8 MiB artifact, 8 PNGs, 2 MiB and
2048 pixels per image. The loader logs neither configuration nor artwork.

## Direct BuildKit builds

An optional `ABBY_MEADOW_ASSETS` secret may instead contain a small JSON
configuration with `endpoint`, `bucket`, `key`, `region`, `accessKeyId`, and
`secretAccessKey`. Pass its file with
`--secret id=ABBY_MEADOW_ASSETS,src=<private-config-file>`; never use a build ARG
for credentials or the artifact itself. Optional nonsecret ARG overrides are
`ABBY_MEADOW_ASSETS_SHA256` and `ABBY_MEADOW_ASSETS_REQUIRED=true`.

Without storage/config secrets, public builds retain authored placeholder art.
The required flag makes missing configuration fatal. A supplied but invalid
configuration, failed download, digest mismatch or incompatible artifact always
fails the build; it cannot silently publish fallback art. Existing local licensed
directories are never replaced by the loader.

Run `npm run test:licensed-art` from `frontend/` for synthetic validation and
mocked S3 transport tests. Their `.check.mjs` filename avoids Vitest discovery.
Rollback selects a previously uploaded key/digest, then rebuilds and redeploys.
