# Coolify 4.1.3 helper restart correction

This is a narrowly scoped, reproducible derivative of the installed Coolify
image. Build-secret deployments resolve `HEAD`, stop their auto-removed helper,
then immediately start another helper with the same deployment UUID. Docker can
release that name after `stop` returns, including after the old container has
disappeared from `ps`/`inspect`. Waiting only for container inspection to fail
does not establish that the replacement can reserve its name.

The derivative retries the same helper `docker run` for at most 60 seconds only
when Docker exits 125 and identifies **that exact helper name** as already in
use. It removes the duplicate stop in the restart method. Other failures return
immediately, successful output is preserved, and an occupied container is never
removed or renamed by the retry. An unrelated Docker connection failure is not
safe to replay as a successful create may have lost its response.

The correction applies platform-wide to future helper starts, with no changes
to application settings, build secrets, routes, databases, or assets. It does
not add deployment queue locking or resolve every possible SSH/Docker failure.

## Exact base and upstream status

The original image is:

```text
ghcr.io/coollabsio/coolify@sha256:7cfd6e20b796024cf7ae5dfcd981b13a0dd3144ba6fb5f533729de4957c05d96
```

This is the security-patched 4.1.3 base observed on November 3, 2026, running
PHP **8.4.27**. The Docker build checks that exact PHP version. Do not rebuild
the older 4.1.2 recipe, downgrade PHP, transplant its complete files, or relax a
guard to get a candidate through.

`apply_patch.php` verifies the complete original bytes of **both** changed PHP
files and `config/constants.php` against the observed image and official
`v4.1.3` sources, and requires the constants to identify exactly 4.1.3. The two
changed files have the same original bytes as the previous recipe; matching
those files alone does not distinguish the releases. It transforms them in
memory before creating a fresh output tree, then publishes that tree with one
directory rename. Source/version drift, a missing input, an existing output,
or reapplication fails closed. It never edits its input tree. A receipt records
the immutable base, PHP version, original and patched hashes, and the
patcher/retry source hashes. Docker builds lint both resulting files before
copying them into the derivative and preserve the base image's user, entrypoint,
command, runtime dependencies, and version.

Two guarded s6 dependency-file additions make nginx and PHP-FPM wait for
`init-script`, preserving the original flat dependency entries. The original
dependency graph is nginx → PHP-FPM and
`init-script` → `init-seeder` → `db-migration`; adding the ingress edges creates
no cycle. Initialization runs CLI PHP and external network requests; it does
not need local HTTP or PHP-FPM. The base image and hashes of the original two
dependency definitions and `app:init` source guard this version-specific change.
The candidate must compile its s6 dependency graph in isolation before activation.
Do not introduce `dependencies.d` alongside the flat nginx dependency file:
s6 gives the directory precedence and would discard the existing PHP-FPM edge.

As checked on 2026-11-03, the released `v4.6.0` still contains the same helper
restart sequence. The relevant upstream correction is
[PR 11626](https://github.com/coollabsio/coolify/pull/11626), open and unmerged
at head `fd6fec6317ff37ee4b0577a71cf2a8b925c808a0`. This implementation follows
its bounded reservation-retry approach and additionally checks the exit code
and exact conflicting name. Upgrading to `4.6.0` alone does not establish that
this race is fixed.

Original source/provenance:

- [Coolify v4.1.3 deployment job](https://github.com/coollabsio/coolify/blob/v4.1.3/app/Jobs/ApplicationDeploymentJob.php)
- [Coolify v4.1.3 Docker helpers](https://github.com/coollabsio/coolify/blob/v4.1.3/bootstrap/helpers/docker.php)
- [Coolify v4.1.3 sudo parser](https://github.com/coollabsio/coolify/blob/v4.1.3/bootstrap/helpers/sudo.php)
- [Coolify v4.1.3 security release](https://github.com/coollabsio/coolify/releases/tag/v4.1.3)
- [Upstream issue 9363](https://github.com/coollabsio/coolify/issues/9363)
- [Latest release checked: v4.6.0](https://github.com/coollabsio/coolify/releases/tag/v4.6.0)

Coolify is copyright its upstream contributors, licensed under
[Apache License 2.0](https://github.com/coollabsio/coolify/blob/v4.1.3/LICENSE).
The derivative retains the upstream source and notices in the base image.
The added correction files are licensed under the same Apache License 2.0;
see [LICENSE](LICENSE). This directory contains no private application source,
credentials, paid asset content, or exported deployment logs.

## Focused tests and candidate build

Use Python 3, PHP 8, and Bash. The tests generate the real Bash command through
`helper_retry.php`; they do not maintain another retry implementation in Python.
The fake Docker accepts only synthetic inputs and exercises delayed name release,
persistent conflicts, unchanged original occupants, argument quoting, Coolify's
non-root sudo rewriting, unrelated errors, other names/exit codes, successful
slow starts, source/version drift, duplicate anchors, and reapplication rejection.
The v4.1.3 `parseLineForSudo` applies the same rewrites as the existing test;
the Dockerfile also checks the complete upstream `sudo.php` hash. No Laravel
bootstrap or private settings are loaded by the tests.

```bash
python3 -m unittest discover -s scripts/operations/coolify_helper -p test_helper_retry.py -v
python3 -m unittest discover -s scripts/operations/coolify_helper -p test_startup_graph.py -v
test -z "$(git status --porcelain -- scripts/operations/coolify_helper)"
helper_patch_head="$(git rev-parse HEAD)"
helper_patch_build="$(date -u +%Y%m%dT%H%M%SZ)-${helper_patch_head}"
docker build --network=none --pull=false \
  --label "lol.bos.coolify-helper-patch.source-commit=${helper_patch_head}" \
  -t "local/coolify:4.1.3-helper-retry-${helper_patch_build}" scripts/operations/coolify_helper
```

If PHP is unavailable locally, `PHP_COMMAND_JSON` may name an operator-controlled
runner that accepts **only the pure PHP test program on stdin** and returns its
stdout, such as an isolated PHP container with its entrypoint overridden. It
must not bootstrap Laravel, load private settings, or print environment values.
`BASH_EXECUTABLE` selects Git Bash on Windows. A skipped test suite is not a pass.
The base image must already be cached for an offline build. Do not replace its
digest or bypass either source hash to get a build through.

Retain a unique tag for each reviewed build and escrow the candidate image
privately. The image declares `coolify.managed=true`, which excludes its tagged
artifact from Coolify's generic unused-image deletion path. A dangling image can
still be pruned, so never move its only retained tag to another build. An owned,
network-isolated holder can protect a candidate while testing and activation are
pending; remove only that holder after the running control plane uses the image.

After building, inspect the candidate's image identity and patch receipt, lint
both files in an isolated process, and run a real Docker reservation test using
uniquely named, network-isolated disposable containers with no production
mounts. Verify delayed release succeeds and a persistent occupied name returns
124 while preserving that original container. Use the produced PHP command,
not a hand-translated substitute. Only owned disposable containers are eligible
for cleanup. Image build and synthetic tests do not themselves prove a live
deployment; keep their evidence distinct.

Run the actual s6 compiler against the verified candidate image ID in isolation:

```bash
python3 scripts/operations/coolify_helper/verify_startup_graph.py sha256:<candidate-image-id>
```

This verifier uses no network or application settings, never runs `/init`, and
checks both original and added direct service dependencies. A failed compile
or a missing original nginx → PHP-FPM edge blocks activation.

## Guarded activation

The operator must capture fresh hashes of the existing Compose files, `.env`,
effective configuration and private application settings; a control database
backup and original image recovery reference; all running workload identities;
and an empty active deployment queue. Keep secrets and backups on the host in a
private recovery directory. Stop if the observed base, source hashes, existing
override, or active work differs from the reviewed state. Do not stop an active
deployment to install this correction.

### Version-native management health check

The November 3 inspection found a management health-check override from a
newer Compose layout: it probes both the HTTP route on port 8080 and a
WebSocket route on port 6001. The pinned 4.1.3 management image does not serve
that latter route; its realtime service is separate. Its own image-native
health-check command succeeds on the current management instance. The helper
derivative inherits that 4.1.3 image-native check, but an existing Compose test
overrides it and would make `--wait` fail even with a correctly built candidate.

Before freezing, capture private hashes of the current override and effective
configuration, plus the exact `Config.Healthcheck.Test` array from the verified
candidate image. Require the candidate test to equal the inspected patched
4.1.3 base image's test, and execute that native command through the trusted
administrator route against the current management container. It must exit
zero before continuing. Do not invent a replacement command, disable health
checks, or use a different release's route to obtain a pass.

The explicitly reviewed effective-configuration allowlist is now exactly
`services.coolify.image` and `services.coolify.healthcheck.test`. Restore the
latter to the exact candidate image-native test. Preserve every other
health-check field, including interval, timeout, retries, start period and any
start interval, and every private environment value, port, mount, network,
service setting and other service. Preserve the original owned override
privately for recovery and refuse concurrent changes. When encoding the test
in Compose, escape each literal `$` as `$$`; then render the proposed merged
configuration in memory and require its decoded test array to equal the
image-native array exactly. Only those two allowlisted paths may differ from
the captured effective configuration. Keep hashes and the comparison receipt
private; do not print expanded configuration, command substitutions or secret
values into chat or Git.

### Drain and activate

Before the final empty-queue check, put the old management instance in
maintenance mode, stop its scheduler service and pause/drain Horizon. Check all
running/reserved queue jobs, application deployments, backup executions and
scheduled tasks, not just application deployment rows. Proceed only after the
management work is empty. Do not kill jobs or clear queues to force this state;
resume the old services and leave maintenance mode if installation is aborted.
Initialization clears the application cache and marks outstanding deployment
rows failed, so maintenance mode alone cannot prevent startup requests from
racing that cleanup. The added s6 dependencies keep both HTTP and PHP ingress
closed until this initialization completes. Wait for fresh management health
before resuming operator requests. The dependency gate also protects incoming
webhooks during cleanup.

The observed Compose project is **`source`**, not `coolify`. Its files include
`/data/coolify/source/docker-compose.yml`, `docker-compose.prod.yml`, and the
existing `docker-compose.custom.yml`. The November 3 inspection found that
custom override already pinning the official 4.1.3 image. Capture its exact
bytes and compare the effective configuration; preserve every setting besides
the deliberately reviewed image and version-native health-test replacement.
Read the current automatic-update preference instead of assuming the initial
October inspection still describes it. Never overwrite an unknown or
concurrently changed override.

Atomically update the reviewed `/data/coolify/source/docker-compose.custom.yml`
so `services.coolify.image` changes to the **verified candidate image ID** and
`services.coolify.healthcheck.test` becomes the verified image-native test,
retaining `pull_policy: never` and all other existing owned settings. Record the
literal image ID in a private installation receipt; a mutable local tag alone
is insufficient recovery evidence. Compare
the effective configuration in memory: all other service definitions and
Coolify mounts, ports, environment, network, user and non-test health settings
must match.
Do not print expanded Compose configuration, which contains secrets.

Using the same trusted SSH session and reviewed files, activate only the
management service:

```bash
cd /data/coolify/source
docker compose --project-name source --env-file .env \
  -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.custom.yml \
  up -d --no-deps --no-build --pull never --force-recreate --wait --wait-timeout 120 coolify
```

Do not use `down`, `--remove-orphans`, the installer, or `upgrade.sh` for this
activation. Recreating only `coolify` refreshes Horizon's persistent PHP workers;
editing the source in the running container alone would neither refresh loaded
classes reliably nor survive recreation. The dashboard is briefly unavailable;
existing deployed applications, the proxy, PostgreSQL and Redis stay running.
Coolify's [instance configuration documentation](https://coolify.io/docs/core/instance-management/environment-variables)
describes custom overrides and this `--no-deps` recreation pattern.

After activation, verify management health, candidate identity, the two patched
source hashes, source receipt, and that the installed container's health-test
array equals the candidate's image-native array. Verify unchanged private
settings/volumes, unchanged workload identities and public app health. Then
validate the normal build-secret
helper restart on an authorized isolated staging deployment before relying on
future production deployments. Do not deploy production merely to demonstrate
this management-service correction.

## Rollback and later platform updates

Keep the exact security-patched 4.1.3 original image locally and the private
configuration/control-DB backup. Never use the historical 4.1.2 image as the
recovery target for this rebase. Before rollback, repeat the guarded freeze
against the **currently running** instance: enter maintenance mode, stop the
scheduler, gracefully drain nginx and PHP-FPM, and prove no admitted request or
CLI producer remains. Pause
Horizon only after other work drains; check all queues and deployment/task/backup
executions twice. Then stop Horizon gracefully with the verified
`/command/s6-svc -wD -T 30000 -O -t /run/service/horizon` and prove its master,
supervisors and workers have exited twice before recreation. A timeout or active
work blocks rollback; never kill jobs or clear queues to force a pass. If
aborting, resume the current instance and verify its health and workers.

A reservation is not completed merely because it is old. Any exceptional
unowned reservation needs a separate private review recording its exact UUID,
raw payload hash and retry score, plus a root-only copy of the raw member.
Only that unchanged member may be excepted; all other work must drain. Prove
all executors exited, preserve its bytes and score through recreation, and
compare them again before accepting rollback. Do not acknowledge, delete,
requeue or reset its attempts as part of rollback.

The original image does **not** contain the new ingress dependencies. Before
using it, prepare two files in the private recovery directory:

- `rollback-nginx-dependencies`: `php-fpm` followed by `init-script`, one per line.
- `rollback-php-fpm-dependencies`: `init-script` followed by a newline.

Keep the parent directory mode `0700`, but make these two nonsecret files
readable by the image's `www-data` user (`0644` was validated). Root-owned `0600`
bind files prevent its unprivileged s6 compiler from starting. Bind them
read-only to `/etc/s6-overlay/s6-rc.d/nginx/dependencies` and
`/etc/s6-overlay/s6-rc.d/php-fpm/dependencies`, respectively, in the final rollback
override. Use long Compose bind syntax with `bind.create_host_path: false`;
a missing source must fail rather than create a directory. Keep the original
flat dependency definitions; adding `dependencies.d` can hide them.

Validate the original image with those exact files **before freezing**. Set
`helper_original_image` to its verified immutable image ID and
`helper_recovery_dir` to the existing absolute recovery path from the private
installation receipt. This offline check runs no initialization or services:

```bash
docker run --rm --pull=never --network=none --read-only --user=www-data \
  --cap-drop=ALL --security-opt=no-new-privileges \
  --pids-limit=64 --memory=128m --cpus=1 \
  --tmpfs=/tmp:rw,nosuid,nodev,size=32m \
  --mount "type=bind,source=${helper_recovery_dir:?}/rollback-nginx-dependencies,target=/etc/s6-overlay/s6-rc.d/nginx/dependencies,readonly" \
  --mount "type=bind,source=${helper_recovery_dir:?}/rollback-php-fpm-dependencies,target=/etc/s6-overlay/s6-rc.d/php-fpm/dependencies,readonly" \
  --entrypoint=/bin/sh "${helper_original_image:?}" -ec '
    export PATH=/command:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    s6-rc-compile -v0 /tmp/rollback-graph /etc/s6-overlay/s6-rc.d /package/admin/s6-overlay/etc/s6-rc/sources
    s6-rc-db -c /tmp/rollback-graph check
    for pair in "nginx php-fpm" "nginx init-script" "php-fpm init-script" \
      "horizon init-script" "scheduler-worker init-script" \
      "init-script init-seeder" "init-seeder db-migration"; do
      set -- $pair
      s6-rc-db -c /tmp/rollback-graph dependencies "$1" | grep -Fxq "$2"
    done'
```

The final rollback override must contain the original image ID, `pull_policy:
never`, the verified version-native health-test correction, and only those two
additional startup-gate binds. Before freezing for rollback, re-inspect the
exact recovery image's native test, prove the encoded/rendered test matches it
with the same dollar escaping, and require the native command to succeed on
the currently running instance. Both this derivative and its 4.1.3 recovery
base use the same native test, so retaining that correction is expected. Do not
blindly restore the pre-repair override's known-incompatible port-6001 test.
Record and independently review the inverse image/health-test diff and the two
gate binds; every other health timing, private setting and service must remain
unchanged. Preserve the prior **owned** override privately, then atomically
install the reviewed rollback
configuration as `/data/coolify/source/docker-compose.custom.yml`; refuse to
overwrite an unknown or concurrently changed override. Compare the effective
configuration in memory; all other settings must match. Include this override
**last** in the same project/files command above and recreate only `coolify`
with `--no-deps --no-build --pull never --force-recreate --wait --wait-timeout
120`. Never rely on the original Compose `${LATEST_IMAGE:-latest}` fallback:
it may select another platform version.

Verify the original image identity, management/app health and preserved workload
identities, environment, mounts, ports and networks. Resume and verify Horizon
and the scheduler, and confirm any preserved reservation is unchanged. Keep the
verified original-image override and both gate binds effective for subsequent
recreations; do not restore the candidate override or a mutable image fallback
after rollback. Retain the dependency files while mounted and record the final
override chain. Rolling forward or upgrading is a separate reviewed operation.
This correction has no database migration and requires no application rollback
or restoration of production data.

The custom image override is an explicit **platform upgrade hold**, not an
automatic patching system. Coolify's official updater preserves custom overrides
and explicitly runs `docker pull` on every configured image. Pulling an image ID
will fail; in the reviewed `v4.1.2` updater this aborts before stopping the current
containers. Do not use the updater while the override is installed, assume a
reported version means the patched image was upgraded, or enable auto-update to
work around this hold. The current auto-update preference remains unchanged.

Before a later manual update: inspect the target release for the upstream fix,
prepare recovery, remove or deliberately rebase this exact owned override,
revalidate native deployment and CI behavior, and verify the actual running
image/version afterwards. A rebase needs new base-image and both source hashes,
fresh patch review, tests and a new image; never transplant the old complete
deployment-job file into a different release. Retire the derivative when a
reviewed official release includes equivalent protection.
