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

## Review binding and focused validation

The former `99ce33ac` runbook is **NOT CLEAN and must not be used to install**.
MAIN's H1, H2 and M1–M5 findings apply to its activation/recovery procedure;
the helper algorithm and pinned image recipe remain unchanged. Every new
source head needs fresh hosted checks, independent Claude review, and MAIN's
per-finding disposition. Evidence for an older head is historical evidence,
not approval of a new head or permission to activate it.

Build only the exact PR head approved independently. A trusted owner/reviewer
supplies a private normalized operator binding manifest and its expected SHA256
through an independent channel. This is an attestation, not the native Claude
receipt format. Do not fabricate a raw receipt path/schema, calculate a digest
from current HEAD and call it approval, or reuse the old-head attestation.
`verify_reviewed_source.py` checks:

- `source`: exact `head`, full `root_tree`, `helper_subtree`, and `expected_base`.
- A clean independent review by Claude of Codex-authored work, bound to that
  same source tuple and the SHA256 of its owner-held raw receipt.
- MAIN's clean disposition of H1, H2, M1, M2, M3, M4 and M5, each with evidence.
- Successful required hosted checks for that exact head/base, including
  `deployment-guards`, and `all_source_gates_clear=true`.
- Clean tracked/untracked Git state, exact HEAD/root/helper trees, expected
  `origin/main`, and base ancestry. Fetch main first; a changed base requires
  renewed review, not rewriting the attestation to match local state.

The manifest schema is defined by the verifier. Its externally supplied digest
is the trust anchor; the script does not authenticate the underlying raw
review or establish runtime admission/installation approval. Keep manifests,
raw receipts and private evidence outside Git. Source gate clearance alone
never clears the activation gates below.

Use Python 3, PHP 8, and Bash:

```bash
python3 -m unittest discover -s scripts/operations/coolify_helper -p 'test_*.py' -v
```

The tests generate the real Bash command through `helper_retry.php`. Synthetic
Docker tests cover delayed release, persistent exact-name conflicts, original
occupant preservation, argument quoting, 4.1.3 sudo rewriting, unrelated errors,
other names/exit codes, slow successful starts, hash/version drift, duplicate
anchors and reapplication. Operator-tool tests use temporary synthetic Git
repositories and Engine snapshots, including port 6001/6002 conflicts,
configuration drift and literal dollar encoding. They do not load Laravel or
private settings. If PHP is absent, `PHP_COMMAND_JSON` may select an isolated
runner accepting only the pure PHP program on stdin; invoke PHP without a `-`
operand. `BASH_EXECUTABLE` selects Git Bash on Windows. Skips are not passes.

Set `helper_build_context` to a new private temporary directory and
`helper_verified_binding_output` to a fresh private receipt file. Fetch main,
then run the binding guard immediately before archiving/building. Derive the
archive revision from its successful verified output, not a separate HEAD
variable or manually copied label. The archive contains only the reviewed
helper subtree. The base must already be cached. Run this block in Bash:

```bash
set -euo pipefail
python3 scripts/operations/coolify_helper/verify_reviewed_source.py \
  --manifest "${helper_binding_manifest:?}" \
  --expected-manifest-sha256 "${helper_binding_sha256:?}" \
  > "${helper_verified_binding_output:?}"
helper_reviewed_head="$(python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["verified"] is True; print(r["source"]["head"])' "${helper_verified_binding_output:?}")"
git archive "${helper_reviewed_head:?}:scripts/operations/coolify_helper" | \
  tar -x -C "${helper_build_context:?}"
docker build --network=none --pull=false \
  --label "lol.bos.coolify-helper-patch.source-commit=${helper_reviewed_head:?}" \
  -t "${helper_unique_candidate_tag:?}" "${helper_build_context:?}"
```

Record the source tuple, context archive hash, patch/build receipt and immutable
candidate image ID. Inspect/lint the changed PHP files and run the full pure PHP
suite against this head. Verify PHP 8.4.27 and unchanged image-inherited runtime
settings. Run the produced helper command in real, uniquely owned, isolated
Docker containers: delayed name release succeeds; a persistently occupied name
returns 124 and preserves its original ID/running state. Clean up only exact
owned disposables. Compile the actual candidate s6 graph as `www-data`, with no
network/private mounts and without running `/init`:

```bash
python3 scripts/operations/coolify_helper/verify_startup_graph.py sha256:<candidate-image-id>
```

A failed compile or lost nginx → PHP-FPM edge blocks activation. Old candidate
runtime receipts must not be attributed automatically to a new source head.
Build/test success does not establish live activation or staging acceptance.

## Durable recovery images and updater hold

Before any freeze, retain both the original security-patched 4.1.3 image and
the candidate by immutable ID, unique unmoved tags, and independently verified
private `docker image save` archives. Verify archive SHA256 and a tested offline
load/identity check in isolation, then verify a durable off-guest escrow copy.
Record exact load/restore steps and storage ownership privately. A registry
repull is only an additional fallback after verifying this same digest remains
available; it is not the only recovery method.

Also keep a uniquely owned **running**, network-isolated holder for each image,
with no published ports, production mounts, application initialization or
credentials. Override the entrypoint with a harmless idle process and verify
that each holder runs the exact expected immutable image. Require both holders
and both archives to exist and remain valid at each freeze and until the
recovery window closes. Tags and `coolify.managed=true` are insufficient:
4.1.3's image-prune label template contains literal quadruple braces and can
select labeled images for deletion. Its container prune can remove eligible
stopped holders before image pruning. Never rely on a stopped holder. Clean up
only holders whose recorded name, ID, ownership label and image all match;
never run global pruning. Retain the recovery base holder after activation.

The image pin **does not stop the updater from rewriting configuration**.
`UpdateCoolify` downloads the configured unversioned CDN `upgrade.sh`; its
Compose and `.env` writes precede the image pull. A later pull failure on an
image ID does not preserve those files. Manual update bypasses the DB-disabled
check. Before freeze require database `is_auto_update_enabled=false`, effective
startup `AUTOUPDATE=false` with no later true override, and no queued/running
updater work. Verify both runtime-effective and startup/disk values; startup
initialization can reapply `AUTOUPDATE` to the database. If absent, true,
unparseable or contradictory, STOP for a separately reviewed correction. Do
not silently change settings under this runbook or invoke any manual updater,
installer or `upgrade.sh` while pinned. Recheck DB and effective startup state
after initialization and on rollback.

Capture hashes of all Compose layers, `.env`, effective service contracts,
private settings and running container identities through the trusted operator
route; retain a private control-DB backup and independently verified off-guest
escrow. Recheck disk **and running** hashes immediately before freeze, before
the atomic override write and before recreation. Any concurrent drift aborts
for renewed review. Never print expanded configuration, environment, secret
build inputs or raw queue payloads in chat, CI logs or Git.

## Application health and actual running contract

Use the official **4.1.3 application** health command for the management service:

```json
["CMD-SHELL", "curl --fail http://127.0.0.1:8080/api/health || exit 1"]
```

Remove only the incompatible newer-layout port-6001 WebSocket clause from this
management test; realtime remains a separate service. The image-native
`/healthcheck` checks generic PHP-FPM ping and can pass while Laravel returns
500 or its dependencies are unreachable. It is not application acceptance.
Require a fresh direct `/api/health` response of **exactly HTTP 200** before
freeze, after activation and after rollback. Do not follow redirects or accept
3xx merely because `curl --fail` returns zero. Preserve interval, timeout,
retries, start period, start interval and every other health setting unless a
specific reconciliation has been independently reviewed.

Preserve the original override bytes privately, but do not assume disk Compose
matches the running instance. The observed project is `source` and uses
`docker-compose.yml`, `docker-compose.prod.yml`, `docker-compose.custom.yml`
and `.env` under `/data/coolify/source`. Newer files can assign management the
separate realtime service's ports 6001/6002, new mounts, environment and network
aliases. A disk-to-disk image/test-only diff can therefore still destroy the
working instance and fail to start its replacement.

Before freeze capture fresh raw Engine inspect snapshots of the running
management service **and every other service**. Independently review the
proposed effective management creation contract against the running contract:
immutable image, entrypoint/command/arguments, all environment/labels/user,
published bindings, mounts and options, networks/aliases/static addresses,
health timings and all HostConfig runtime/security/resource settings. Preserve
other services byte/value-for-value. The default intended changes are the
candidate image and application health test; **any existing disk/runtime drift
requires an explicit minimal reconciliation, independent review and a proven
recovery contract before freeze**. Do not carry drift into recovery.

`verify_activation_contract.py` compares supplied Engine-shaped snapshots,
retaining all Config/HostConfig fields, mounts and network creation fields. It
omits only generated hostname/address/endpoint identity, retaining requested
static IPAM and aliases. Unknown network creation fields remain comparable.
Its exact-change manifest has `schema_version: 1` and `changes`, a list of
`{path, before, after}` JSON-pointer entries; the set must equal the complete
actual diff. No wildcard paths or implicit allowlist. Supply the independently
reviewed manifest's expected SHA256. Values and diffs remain private; failures
print no configuration. Capture and review snapshot hashes/provenance too:
matching arbitrary supplied files does not prove correspondence to a host.

A safe never-started, uniquely owned, network-none probe may establish image
inherited defaults and the Engine health-test array. **It does not establish
production mounts, networks, aliases or the full creation contract.** Never
join a probe to production networks or mount production paths merely to get a
passing comparison. A safe explicit service projection must preserve all
creation fields, reject unsupported settings, and receive independent review;
this repository does not implement a Compose-to-Engine projector. If equivalent
proposed/recovery contract evidence cannot be obtained safely, STOP. Do not
present the network-none probe as full service validation.

Render the proposed merged Compose configuration **with interpolation enabled**.
Require the source test's literal dollar encoding (`$` → `$$`), decode exactly
one dollar layer from default Compose JSON, and compare the actual created
probe's `Config.Healthcheck.Test` to the approved application array. Do not use
`--no-interpolate` or repeatedly decode to obtain a pass. The current command
contains no dollars; synthetic guard tests retain coverage for future commands.
The verifier's private health evidence fields are `encoded`, `rendered`,
`engine` and `interpolated: true`:

```bash
python3 scripts/operations/coolify_helper/verify_activation_contract.py \
  --running "${helper_running_inspect:?}" --proposed "${helper_proposed_inspect:?}" \
  --other-containers "${helper_all_containers_inspect:?}" \
  --reviewed-changes "${helper_exact_changes:?}" \
  --expected-changes-sha256 "${helper_exact_changes_sha256:?}" \
  --health-evidence "${helper_health_evidence:?}"
```

Require a complete fresh live container/host-listener inventory as well. The
verifier rejects conflicting published TCP/UDP ports in the supplied running
container inventory, including separate realtime ownership of 6001/6002. It
cannot certify inventory completeness, non-Docker listeners or changing port
availability. Check those independently immediately before freeze. Any conflict
or unsupported/ambiguous automatic host binding blocks recreation; do not stop
another service to free its ports.

## Owner-controlled admission hold and drained activation

**No installation is authorized while admission closure or the drain is
unproven.** Prepare a concrete target list, bounded owner window, evidence and
restore plan if owner actions are needed. This desktop lane must not change
abby-loop state, take over its tasks, modify unrelated application auto-deploy
settings, add credentials/connections, or silently change environment/network/
webhook settings. MAIN holds PR366, PR359 and other merges capable of native
auto-deployment. Merging this PR is not the repair: it triggers normal main
CI/CD/webhooks, and does not install the management derivative.

The owner must confirm a reviewed hold covering **all** deployment admission
sources: abby-loop and other merge producers, all control-plane automatic and
preview webhooks, hosted pipelines, manual/API/CLI operators and recurring
producers. Verify admission closure independently and show it persists across
management recreation, until explicit staging-only release. Maintenance mode
alone is insufficient: `webhooks/*` is exempt, and maintenance state may not
persist through initialization. Do not discard queued production work to make
the gate pass. If persistence cannot be proven, STOP and propose the additional
technical gate for separate review/approval; no blanket permission is implied.

Within that owner-approved hold, check HTTP 200 and fresh disk/runtime hashes,
then enter maintenance, stop the scheduler and close/drain nginx **and**
PHP-FPM gracefully. Prove no admitted request or independent CLI producer
remains. Let existing work finish; then pause/drain Horizon and check all
Redis ready/delayed/reserved/processing queues and every deployment, console
job, scheduled task and backup execution twice. A reserved cleanup job blocks
the gate just like other work; age is not completion. Do not acknowledge,
except, delete, requeue, reset attempts, kill jobs or clear queues to force a
pass. Abort and resume the old service if the gate cannot clear.

Only after other work drains, stop Horizon gracefully with the reviewed
`/command/s6-svc -wD -T 30000 -O -t /run/service/horizon`. Prove its master,
supervisors and workers exited and repeat the empty/PID check. A timeout or
remaining executor blocks recreation. Recheck the owner hold, source binding,
image holders/escrow, disk/running snapshots, exact contract/recovery diffs and
host-port ownership. Record the complete private freeze receipt.

The added nginx/PHP-FPM s6 edges protect initialization only; **Horizon and the
scheduler start automatically after initialization**. The external/persistent
admission hold and genuinely empty queues must already make that safe before
recreation. The ingress dependencies do not implement an ongoing staging-only
queue hold. Keep application discovery disabled. No production jobs may run
before the explicitly authorized isolated staging app/revision has validated
the normal build-secret helper restart path.

Atomically install only the reviewed owned management override with immutable
candidate image ID, `pull_policy: never`, the application health test, and any
explicitly approved minimal reconciliation. Refuse concurrent/unknown changes.
Keep prior bytes and the separately prevalidated recovery override; preserve
every other service. Using only the reviewed file chain:

```bash
cd /data/coolify/source
docker compose --project-name source --env-file .env \
  -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.custom.yml \
  up -d --no-deps --no-build --pull never --force-recreate --wait --wait-timeout 120 coolify
```

Do not use `down`, `--remove-orphans`, installer, updater or a full-stack
recreation. On success verify Engine image/patch receipt/hashes, PHP 8.4.27,
actual health test and HTTP 200, private runtime/disk contract, unchanged other
workload identities and public application health. Recheck the updater hold,
all queues/executions and PID state immediately after initialization, while
external admission remains closed. Unexpected work blocks release; do not clear
it or let it become an unplanned production deployment.

Only then may the owner authorize admission of **one exact isolated staging
application/revision**, preserving its normal build secrets and helper restart
path, while every production producer remains held. Verify successful staging
and original-occupant preservation. If safe selective admission cannot be
proven, leave the hold in place and STOP for a reviewed plan. After this proof
and MAIN acceptance, MAIN owns subsequent PR merges and production release;
the owner restores only the recorded holds in the approved restore plan.

## Failed recreation and guarded rollback

A nonzero `up --wait` is a failure, even if the old container has disappeared.
Do not retry blindly: capture the current Engine/container/error state privately
and keep external admission closed. Determine whether the old immutable
container still runs, the candidate runs but is unhealthy, or only a Created/
exited replacement remains. If the old instance still runs, resume it only
under the reviewed abort/restore plan and verify application HTTP 200. If it
has been removed, use the **prevalidated recovery contract**, never whichever
Compose bytes happen to be on disk after the failure. A known failed Created
replacement is eligible for removal only after its exact recorded ID/name,
ownership, stopped state and lack of admitted work are verified; preserve
failure evidence first. Unknown or active state requires operator recovery,
not deletion or retry.

The same admission, hash, drain, queue/PID and port gates apply to rollback.
When a failed recreation leaves no running management process, prove absence
of all management executors/admitted requests and externally inspect queues/
execution state rather than assuming absence means drained. Do not run the
freeze commands against an unrelated or missing container. A missing gate or
active reservation blocks automatic recovery; escalate with holds intact.

Recover only to the original security-patched **4.1.3/PHP 8.4.27** image. Its
original startup graph lacks the new ingress dependencies, so prepare these
nonsecret files under the private recovery directory before any activation:

- `rollback-nginx-dependencies`: `php-fpm` then `init-script`, each newline-terminated.
- `rollback-php-fpm-dependencies`: `init-script` followed by a newline.

The parent directory remains `0700`; make the two files `0644` so `www-data`
can read them. Bind read-only to each matching
`/etc/s6-overlay/s6-rc.d/<service>/dependencies` using long syntax and
`bind.create_host_path: false`. Do not add `dependencies.d`. Validate the exact
original image plus these binds with the real s6 compiler/checker as `www-data`
in isolation before freeze; require nginx→PHP-FPM, both ingress→init-script,
Horizon/scheduler→init-script and init-script→init-seeder→db-migration. No `/init`,
network or private mounts are needed for that check.

The independent recovery review must bind exact base image ID, tested gate
binds, the application health test, `pull_policy: never`, and any minimal
reconciliation required to reproduce the **previous running** contract. Compare
recovery against actual running state and against intended preserved state;
review the inverse image/test diff and only these extra gate mounts. Recheck
health dollar encoding/actual probe test. Do not restore the known-incompatible
6001 clause, drifted layout, mutable `${LATEST_IMAGE:-latest}` fallback, or an
unreviewed change. Prevalidate port ownership and a safe complete recovery
contract before the original instance is removed.

Atomically install the exact reviewed recovery override last in the preserved
file chain and recreate only `coolify` with the same bounded `--no-deps
--no-build --pull never --force-recreate --wait` procedure. If recovery itself
fails, keep holds and evidence, stop retries and use the independently reviewed
operator recovery plan/offline escrow. Never broaden to full-stack teardown.
After recovery require HTTP 200, exact image/PHP/source identity, expected
actual health test, private preserved settings/volumes/networks/ports, other
workload identities, updater hold and queues/executions; release producers only
through the approved restore plan. Retain the recovery override, gate files,
image holders and escrow for the recovery window. No application database
migration, production data restore or application rollback is part of this
source correction.

A future platform upgrade is a separate reviewed operation: check the target
for the upstream fix, deliberately remove/rebase this owned override, renew
base/source/startup guards and tests, and verify actual image/runtime behavior.
Never transplant complete old job files or assume a reported version proves
this derivative was installed. Retire it once a reviewed official release
contains equivalent protection.
