# Shared avatar production handoff

This is preparation, not authorization to merge or deploy. PR #225 introduces
the shared runtime, importer, Docker secret scoping and Profile integration as
well as Archer 1.0.2. Review that whole change, not just its final asset pin.

## Recorded state and merge hold

Read-only checks on 15 October 2026 found:

| Item | Observed state |
| --- | --- |
| Repository / PR | `sock-lint/the-abby-project`, [PR #225](https://github.com/sock-lint/the-abby-project/pull/225), target `main` |
| Fetched `origin/main` | `df5f76022e7a74c99771bf40b111ee39d688b5b7`; ancestor of the task branch, zero commits behind |
| Runtime-accepted staging source | `efa03fb1306975f7d77fa1bcb4dade36484ef3d3` |
| Staging application | `js8l9rtqtitsfa2uyei8ltcl`, exact source above, `/docker-compose.staging-cloudflare.yml` |
| Production application | `lr5dn6lhga31vyk6u5qvhm4c`, `main`, configured `HEAD`, `/docker-compose.yml`, normal native Compose |
| Production controls | Automatic deployment **enabled**, preview disabled, Build Secrets enabled |
| Staging controls | Automatic/preview deployment disabled, raw Compose and preserve-repository enabled |

Documentation commits may advance the PR branch. They do not change staging's
pinned runtime source. Do not describe a later documentation head as deployed.
Recheck main, the PR head and live settings immediately before a future release.

**Stop before merging.** A push to `main` can trigger Coolify's native webhook
before Actions validation completes. Actions' current-main, build and scan gates
do not control that webhook. Preparation changed neither live deployment controls
nor Cloudflare. Resolve production/public-delivery decisions and the deployment
window before merging; do not treat merge as a harmless intermediate step.

The live staging source still names `codex/shared-avatar-assets-staging`.
GitHub may delete that PR head on merge even though its pinned SHA remains in
history. Hold merge/branch cleanup until staging is moved to an approved durable
source ref in a separately authorized, verified staging deployment. Preserve the
local branch while the active checkout or live application depends on it. This
preparation does not retarget staging, deploy it or disable automatic PR-branch
deletion. The owning cleanup monitor must retain the active dependency.

The owned task-branch push was checked separately: production selects `main`,
both applications have previews disabled, and staging auto-deploy is disabled.
Installed Coolify 4.1.2 `Webhook/Github.php` selects the pushed branch before
`isDeployable()`; PR events require `isPRDeployable()`. The GitHub CI/CD workflow
also deploys only `main`. Recheck these point-in-time conditions before later
pushes rather than assuming they remain unchanged.

## Public delivery and acceptance

Existing Abby hosting remains public. Owner-only Cloudflare Access was accepted
for staging; that is not public-delivery acceptance for the new shared wardrobe.
The shared importer validates bytes/contracts but does not enforce the legacy
artifact's `delivery_review` marker.

Before public promotion, reference an existing acceptance that actually covers
this release or record the applicable owner decision against the exact digest,
licensed pack/seats, wardrobe and public browser delivery. Preserve the prior v2
decision within its scope; do not silently extend it. See the
[owner prerequisite](licensed-avatar-art.md#owner-release-prerequisite) and
[wardrobe boundary](licensed-avatar-art.md#supplied-wardrobe). Do not rewrite an
immutable manifest to manufacture a marker.

Private storage/build credentials do not make delivered GLBs private: Vite emits
runtime files under `/static/assets/`, served by WhiteNoise. App login protects
API data, not these static files. Do not replace production's existing hosting
or authentication with staging Access rules during this preparation.

Desktop staging accepted automatic Idle, equipment fit, Profile/wardrobe, PWA
update/session continuity, saved state, hashes and origin isolation. Phone
graphics/performance acceptance remains pending. Signed native shells and their
Access/session flow are a separate release track.

## Configuration delta

`frontend/assets.lock.json` already pins family `meshtint-female-archer-pack-01`,
version `1.0.2`, manifest
`4814589d481fcac4e51a62c7af8e7b4a4e1cf593fde670a281d49480bef09cb3`, directory
`meshtint-female-archer-pack-01/1.0.2/4814589d481fcac4e51a62c7af8e7b4a4e1cf593fde670a281d49480bef09cb3`.
The inventory is 105 files / 93,088,255 bytes; runtime/vendor packages stay `1.0.0`.

The seven production shared-reader settings are **already configured** and equal
to the reader values used by verified staging. No value needs copying and no new
setting is proposed:

| Setting | Desired state, already observed |
| --- | --- |
| `ABBY_ASSETS_S3_ENDPOINT` | Existing HTTPS Spaces endpoint |
| `ABBY_ASSETS_S3_REGION` | Existing reader region |
| `ABBY_ASSETS_S3_BUCKET` | Existing private runtime bucket |
| `ABBY_ASSETS_S3_PREFIX` | Existing `releases` prefix |
| `ABBY_SHARED_ASSETS_REQUIRED` | Existing true requirement; never disable to hide an import failure |
| `ABBY_ASSETS_ACCESS_KEY_ID` | Existing dedicated read-only runtime reader, not publisher/source-backup access |
| `ABBY_ASSETS_SECRET_ACCESS_KEY` | Existing matching secret; do not print or copy here |

Each has build-time enabled, runtime disabled and literal-value disabled, with
no preview row. Inventory: 120 environment rows, these seven plus **113 unrelated
rows**. Preserve every unrelated value and flag. Preserve media/AWS credentials,
signing/database keys, signup/email policy, Sentry, volumes, printer and worker
configuration. Do not copy staging's Compose recipe, synthetic credentials/seeder
or disabled-service policy into production. Preserve generated `SOURCE_COMMIT`;
do not create an operator-maintained row.

Build Secrets is already enabled; keep it enabled. The reviewed Dockerfile scopes
every RUN mount. The public GHCR validation image contains no purchased runtime
and is not the production artifact. Native Coolify must build reviewed main using
its preserved private inputs. A lock change invalidates the import layer; later
authorized credential changes need a build without cache because secret contents
alone do not invalidate Docker layers.

## Freeze and recovery handoff

Private baseline:
`C:/Users/socce/Documents/AbbyAssets/.local/spaces/production-preparation-before.json`.
It records six services, environment/volume fingerprints and 222 migration IDs
(aggregate `eb2cb86b23b68a030a1c1476b146809977a75cd56d549f25d851e2953349af28`).
This read-only inventory is not a database backup or restore test.

| Item | Recorded reference; refresh before release |
| --- | --- |
| Healthy source | `df5f76022e7a74c99771bf40b111ee39d688b5b7` |
| Last successful native deployment | `bsf2kds1avnjahy3b6pc33b5` |
| Running Django image | `sha256:5a5e5c5e4be4df55435665e056ae879661179f92190d20bf1306c4531630ab0e` |
| Mutable image tag | `the-abby-project`; not an immutable recovery reference |
| PostgreSQL volume | `lr5dn6lhga31vyk6u5qvhm4c_postgres-data` |
| Redis volume | `lr5dn6lhga31vyk6u5qvhm4c_redis-data` |

The later failed attempt `tunliwfhusz800zf05v0t2lo` at the same SHA is not the
last-good deployment. Refresh the freeze after any other production change.
The workshop source backup does not back up production DB data, user media,
mounts or application configuration.

Before a future approved merge, the production operator must escrow current
application images and create/verify a private DB recovery dump. These Linux-host
commands are **future steps, not executed by this preparation**. They do not
restore, stop or deploy production:

```sh
set -eu
prod_app=lr5dn6lhga31vyk6u5qvhm4c
prod_recovery_dir="/root/abby-production-recovery/$prod_app/$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$prod_recovery_dir"
set -- $(docker ps -q --filter "label=com.docker.compose.project=$prod_app" --filter label=com.docker.compose.service=db)
[ "$#" -eq 1 ]
prod_db_container=$1
[ "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' "$prod_db_container")" = "$prod_app" ]
docker exec "$prod_db_container" sh -c 'exec pg_dump --format=custom --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' > "$prod_recovery_dir/database.dump"
test -s "$prod_recovery_dir/database.dump"
docker exec -i "$prod_db_container" pg_restore --list < "$prod_recovery_dir/database.dump" > "$prod_recovery_dir/database.catalog"
prod_prior_image=sha256:5a5e5c5e4be4df55435665e056ae879661179f92190d20bf1306c4531630ab0e
docker image inspect "$prod_prior_image" --format '{{.Id}}' > "$prod_recovery_dir/image.id"
docker image save --output "$prod_recovery_dir/application-image.tar" "$prod_prior_image"
sha256sum "$prod_recovery_dir/database.dump" "$prod_recovery_dir/application-image.tar" > "$prod_recovery_dir/SHA256SUMS"
chmod 600 "$prod_recovery_dir"/*
```

Replace the image ID if a refreshed freeze identifies another current image;
compare all six services and escrow any additional application image IDs.
Preserve user-media/mount backups and secure configuration recovery through the
existing operator process. Record private paths, sizes, hashes, timestamp, image
IDs and successful catalog validation without exposing contents or secrets.
Then rehearse a full restore in a disposable isolated DB with no production app,
host ports, mail, printer or scheduler attached. `pg_restore --list` is not that
rehearsal. Production dump/image escrow and full restore rehearsal remain pending.

## Future release validation

After explicit promotion/public-delivery decisions, fresh backups and the agreed
window, merge the reviewed full PR through the normal process. Observe native
webhooks as well as Actions; do not queue an extra deployment just because both
paths exist. Follow [platform deployment](platform-deployment.md), correlating
finished native SHA, running `SOURCE_COMMIT` and public serving health identity
with the actual resulting main commit, which may differ from the PR head.

Require all 105 served hashes, the exact manifest, new PWA-client adoption,
automatic Idle and fitted equipment. Use approved production observer/accounts
for login, Profile, saved-look reload and family-boundary checks. Never use
staging credentials or seed synthetic users into production. Check production's
own media/CORS/auth behavior; the staging owner-Access session does not cover it.
A health-only pass does not exercise all six production services.

## Rollback choices

Do not use an old workflow dispatch, deploy the public fallback-only GHCR image,
rewrite main or substitute raw Compose. Source rollback is a new reviewed
current-main change with current CI and the same merge/deploy hold. Preserve
immutable release objects and recovery artifacts.

For an **asset-only regression**, retained 1.0.1 is a candidate with the same
saved IDs/runtime versions. Use it publicly only when applicable delivery
acceptance covers it; private staging is not that acceptance. Use a fresh owned
checkout/branch from current main, replace `YYYYMMDD`, and select a verified
private release directory:

```powershell
git fetch origin --prune
git switch -c codex/rollback-archer-release-YYYYMMDD origin/main
@'
from pathlib import Path
import json
p = Path('frontend/assets.lock.json')
lock = json.loads(p.read_text())
pin = next(x for x in lock['releases'] if x['family_id'] == 'meshtint-female-archer-pack-01')
assert pin['release_version'] == '1.0.2'
assert pin['manifest_sha256'] == '4814589d481fcac4e51a62c7af8e7b4a4e1cf593fde670a281d49480bef09cb3'
digest = '6bf2632e77fb5990fb0db0aab07674cf40d5af2c4dcf22ecb8238abb3d52e2d1'
pin.update(release_version='1.0.1', manifest_sha256=digest, directory='meshtint-female-archer-pack-01/1.0.1/' + digest)
p.write_text(json.dumps(lock, indent=2) + '\n')
'@ | python -
$env:ABBY_ASSETS_RELEASE_ROOT = '<verified private directory containing the retained release>'
$env:ABBY_COMPANION_WORKSPACE = '<fully extracted verified roster verification workspace>'
npm --prefix frontend run assets:import
npm --prefix frontend run assets:verify
npm --prefix frontend run test:run -- src/avatar/sharedRelease.test.js src/avatar/AvatarScene.test.jsx
npm --prefix frontend run build
git diff --check
git add -- frontend/assets.lock.json
git commit -m 'Restore the reviewed prior Archer release'
git push -u origin HEAD
```

Create/review the rollback PR, validate/stage its exact source, then use the
authorized main process. These commands do not merge or deploy. If main changed
release or saved IDs, assertions intentionally stop; reassess compatibility.
The workspace setting is required for this fresh offline checkout because the
release tree does not contain the seven supplemental companion portraits. An
existing installed supplemental tree can instead be reused without the workspace
or S3 reader only when its exact inventory, hashes and pin verify. If neither a
valid installed tree nor a verified workspace or configured reader is available,
the importer fails with the missing-source action before replacing release
files. Preserve that failure and provide the required source; do not bypass the
supplemental checks.

For a **full integration regression**, a pin rollback does not revert loader,
runtime, Docker or UI code. Verify PR #225's actual merge method and complete
landed diff. In a fresh current-main incident branch, choose exactly one:

```powershell
# Verified two-parent merge commit for the complete PR:
$verifiedMergeCommit = 'REPLACE_WITH_VERIFIED_PR225_MERGE_SHA'
if ($verifiedMergeCommit -notmatch '^[0-9a-f]{40}$') { throw 'Verify the complete merge first' }
git revert -m 1 --no-edit $verifiedMergeCommit
```

```powershell
# Verified squash commit containing the complete PR:
$verifiedSquashCommit = 'REPLACE_WITH_VERIFIED_PR225_SQUASH_SHA'
if ($verifiedSquashCommit -notmatch '^[0-9a-f]{40}$') { throw 'Verify the complete squash first' }
git revert --no-edit $verifiedSquashCommit
```

For a rebase merge, enumerate/review all landed integration commits; the last
rebased commit alone is not the whole PR. Do not infer squash versus rebase from
one parent. Resolve conflicts without losing later unrelated work, then push a
normal reviewed rollback PR and run the normal gates.

PR #225 adds no Django migration or production content change relative to its
recorded base. Do not restore an old DB merely to roll back this asset/UI work.
If another main change introduces incompatible schema/data, prefer a reviewed
forward fix and verify old-code compatibility. Any destructive restore is a
separate incident operation with quiesced writers, affected-worker/printer
coordination, verified recovery artifacts and explicit data-loss/restore review.
No DB downgrade, restore, image installation or production deployment ran here.
