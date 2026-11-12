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

The former `99ce33ac`, `c8d10b60`, `b7a5335a`, `0ba82ffc`, `92243170` and
`34736af6` and `09bc7fa2` revisions are
**NOT CLEAN and must not be
used to install**. MAIN's H1, H2, M1–M5 and subsequent ACT-1, ACT-2, SG-1 and
README-1 findings apply to their activation/recovery procedures. Later N1–N5,
SG-2, RB-1 and RV366G-RB1-A/B findings also require fresh independent dispositions;
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
- MAIN's clean disposition of all twenty mandatory gated finding IDs, including
  N1–N5, SG-2, RB-1 and RV366G-RB1-A/B,
  each with evidence; missing or unresolved current findings reject.
- Successful required hosted checks for that exact head/base, including
  `deployment-guards`, and `all_source_gates_clear=true`.
- Clean tracked/untracked Git state, exact HEAD/root/helper trees, expected
  `origin/main`, and base ancestry. Fetch main first; a changed base requires
  renewed review, not rewriting the attestation to match local state.
- Schema 4 `build_inputs`: reviewed raw-blob SHA256 for `Dockerfile`,
  `apply_patch.php` and `helper_retry.php`, and independently pinned
  `canonical_tar_sha256` for the entire helper subtree.
- A separate closed `operator_tools` map pins all six executed entry/sibling
  sources: this verifier, the startup verifier, the activation driver, its
  projection/comparison modules, and `trusted_operator_loader.py`. Docker build
  inputs cannot authenticate the process doing verification. The executed
  verifier and loader pins must match this same approved manifest.

The manifest schema is defined by the verifier. Its externally supplied digest
is the trust anchor; the script does not authenticate the underlying raw
review or establish runtime admission/installation approval. Keep manifests,
raw receipts and private evidence outside Git. Source gate clearance alone
never clears the activation gates below.

The closed twenty-ID guard is not a count of every observation in the raw
review. MAIN's `92243170` review reports 0 high, 2 verified medium, 22 low and
4 informational observations, with 3 reviewers, 5 verifier jobs, 28 confirmed
and 1 unverified item in its retained review trail. The two new mandatory IDs
are RV366G-RB1-A and RV366G-RB1-B. Other low/informational observations remain
in the coordinator-held report; this change does not invent dispositions or
claim they were all fixed. The former clean reviews and source/runtime receipts
cannot clear this new head or the unresolved operational boundary.

Native Claude review of exact `34736af6`, completed `2026-11-03T22:54:04Z`,
returned FINDINGS with one LOW `freeze-receipt-digest-never-checked`: the old
driver checked only a 64-hex string. The raw-byte/path correction below requires
fresh independent review. This LOW is not silently added to the twenty-ID MAIN
gate. MAIN's formal `34736af6` disposition below is separate; neither review is
represented as clean current-head approval.

MAIN's later formal `34736af6` disposition is **NOT CLEAN** with two verified
medium subfindings, `RB1A-H1` and `RB1A-H2`, under the existing
RV366G-RB1-A gate. Static reading confirms the same omitted effects in
`f17932c3`. StandaloneDocker creation has inline network effects, and the
dispatched proxy/Sentinel actions have substantial execution descendants.
Rows A13–A16 in [STARTUP_REVIEW.md](STARTUP_REVIEW.md) now give separate
predicates, target/effect counts to verify and STOP rules. These subfindings do
not expand the twenty mandatory IDs. Fresh review is required; no Native Claude
or MAIN verdict for a different head is inferred.
The full MAIN `34736af6` packet records 29 confirmed observations: 2 medium,
18 low and 9 informational. Its two mandatory medium subfindings are addressed
here for renewed review. Uncorrected low/informational observations remain in
the coordinator-held raw trail; no blanket fixed/accepted disposition is made.
Historical Native Claude review of `f17932c3` was CLEAN with empty findings at
`2026-11-03T23:27:00Z`, from code reading only with no reviewer tests. MAIN's
formal `f17932c3` disposition at `2026-11-03T23:39:12Z` accepted the opaque
receipt-integrity component but remained overall NOT CLEAN for the two carryover
medium findings, with residual 4 LOW/4 INFO review data. Neither applies
automatically to this next head.

MAIN's final `09bc7fa2` disposition at `2026-11-04T00:09:33Z` is **NOT CLEAN**:
0 high, 1 verified medium, 10 low and 11 informational observations. Inline
network H1 is fixed; H2 remains partial for `RV366J-H2-1`, an already-running
Sentinel's recurring push/admission and descendant closure. The new A17–A18
requirements remain under the existing RV366G-RB1-A/H2 gate; mandatory IDs stay
twenty. Native Claude's clean `09bc7fa2` code-only review is historical for this
new head and does not clear MAIN or runtime gates. Uncorrected low/informational
observations retain their actual review qualifications; no blanket disposition
or new operational authorization is inferred.

Use Python 3, PHP 8, and Bash. During the current operational review hold, the
allowed local subset is limited to harmless policy, constant-module, standard
library isolation and status-schema cases:

```bash
cd scripts/operations/coolify_helper
PYTHONDONTWRITEBYTECODE=1 python3 -B -W error::ResourceWarning -m unittest \
  test_operator_source_policy test_safe_operator_bootstrap \
  test_freeze_receipt_policy -v
```

The broader existing suites are not rerun locally under that hold. They
generate the real Bash command through `helper_retry.php`. Synthetic
Docker tests cover delayed release, persistent exact-name conflicts, original
occupant preservation, argument quoting, 4.1.3 sudo rewriting, unrelated errors,
other names/exit codes, slow successful starts, hash/version drift, duplicate
anchors and reapplication. Operator-tool tests use temporary synthetic Git
repositories and Engine snapshots, including port 6001/6002 conflicts,
configuration drift and literal dollar encoding. They do not load Laravel or
private settings. If PHP is absent, `PHP_COMMAND_JSON` may select an isolated
runner accepting only the pure PHP program on stdin; invoke PHP without a `-`
operand. `BASH_EXECUTABLE` selects Git Bash on Windows. Skips are not passes.

Every operator entry must run through the following trusted inline bootstrap
with `python3 -I -S -B`; plain checkout-script execution is not a verified path.
Obtain the loader's own SHA256 independently from the **same** approved manifest.
The inline code reads a regular loader file once, verifies that captured buffer,
then compiles and executes those same bytes. Do not replace it with a separate
hash command followed by reopening the script. Copy this reviewed inline code
directly; an unverified checkout bootstrap is not a trust anchor. Set
`helper_tools_dir` to the canonical absolute helper directory and define:

```bash
helper_operator() {
  python3 -I -S -B - "${helper_tools_dir:?}/trusted_operator_loader.py" \
    "${helper_loader_sha256:?}" "$@" <<'PY'
import hashlib, os, pathlib, re, stat, sys
path = pathlib.Path(sys.argv[1])
expected = sys.argv[2]
if not path.is_absolute() or path.resolve() != path or not re.fullmatch(r"[0-9a-f]{64}", expected):
    raise SystemExit("Independent canonical loader pin required")
fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
with os.fdopen(fd, "rb") as stream:
    if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
        raise SystemExit("Regular loader source required")
    source = stream.read(16 * 1024 * 1024 + 1)
if len(source) > 16 * 1024 * 1024 or hashlib.sha256(source).hexdigest() != expected:
    raise SystemExit("Captured loader digest mismatch")
sys.argv = [str(path), *sys.argv[3:]]
namespace = {"__name__": "__main__", "__file__": str(path),
             "_TRUSTED_OPERATOR_ENTRY_SHA256": expected}
exec(compile(source, str(path), "exec"), namespace)
PY
}
```

The loader captures and verifies the independently SHA-pinned raw manifest
before loading a standalone entry. For the driver, it captures the independently
SHA-pinned raw plan, binds its three source hashes to that same approved
manifest, and captures **all three** entry/sibling source buffers before any
executes. Sibling imports resolve only the verified in-memory modules; there is
no checkout search-path insertion, bytecode loading, or source reopening.

Set `helper_build_context` to a **not-yet-existing** private export path outside
the checkout, and `helper_verified_binding_output` to a fresh private receipt
file. Fetch main, then run the guard. It disables replacement/config/attribute
overrides, rejects unsafe repository state, exports raw `ls-tree`/`cat-file`
objects, and independently reconstructs the exact tree, file modes and input
SHA256. A canonical TAR is captured and independently parsed/rehashed, then
checked against the external manifest. With the optional build flag, Docker
consumes those **same immutable in-memory TAR bytes** on stdin in that process.
It does not consume the mutable diagnostic export directory. Without that
flag, the command only verifies/captures and makes no Docker call. The unique
tag must not exist; the base must already be cached. Ignored/excluded helper
files reject. Preserve any known test-generated `__pycache__` outside the
checkout with an ownership record before verification; do not broadly clean or
delete other work. The following is a future gated build procedure, not
permission to build during the current operational hold:

```bash
set -euo pipefail
helper_operator standalone --tool-dir "${helper_tools_dir:?}" \
  --entry verify_reviewed_source.py \
  --expected-entry-sha256 "${helper_verifier_sha256:?}" \
  --operator-manifest "${helper_binding_manifest:?}" \
  --expected-operator-manifest-sha256 "${helper_binding_sha256:?}" -- \
  --manifest "${helper_binding_manifest:?}" \
  --expected-manifest-sha256 "${helper_binding_sha256:?}" \
  --export-context "${helper_build_context:?}" \
  --build-candidate-tag "${helper_unique_candidate_tag:?}" \
  > "${helper_verified_binding_output:?}"
```

Record the source tuple, actual consumed canonical TAR SHA, patch/build receipt
and returned `built_image_id`. The build writes a fresh uniquely owned IIDfile;
its captured immutable ID and independent ID/tag inspections must agree.
Unknown OCI index/selected-ID ambiguity is a HOLD, never mutable-tag inference.
Compare its embedded `patcher_sha256` and
`retry_source_sha256` against the trusted reviewed raw-blob build inputs. The
source guard returns expected values and explicitly does **not** claim this
image receipt check passed. Never substitute `git archive`, an inherited filter
or a mutable directory as the build input. Inspect/lint the changed PHP files and run the full pure PHP
suite against this head. Verify PHP 8.4.27 and unchanged image-inherited runtime
settings. Run the produced helper command in real, uniquely owned, isolated
Docker containers: delayed name release succeeds; a persistently occupied name
returns 124 and preserves its original ID/running state. Clean up only exact
owned disposables. Compile the actual candidate s6 graph as `www-data`, with no
network/private mounts and without running `/init`:

```bash
helper_operator standalone --tool-dir "${helper_tools_dir:?}" \
  --entry verify_startup_graph.py \
  --expected-entry-sha256 "${helper_startup_verifier_sha256:?}" \
  --operator-manifest "${helper_binding_manifest:?}" \
  --expected-operator-manifest-sha256 "${helper_binding_sha256:?}" -- \
  "${helper_candidate_image_id:?}"
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

`capture_activation_contract.py` is the authoritative chain/probe driver. Its
externally approved plan binds the **actual ordered Compose files and `.env`
bytes**, actual interpolated render, service config hash, actual Compose version,
running container ID, candidate image ID, project/service identity, ownership
nonce and exact operator-tool source SHA256. No operator-supplied proposed
Engine snapshot or health assertion is accepted. `verify_activation_contract.py`
is an offline comparison helper; its supplied-file result cannot authorize
activation.

The driver itself queries the actual chain, derives a fresh owner-labeled
network-none/port-free/private-mount-free recipe, and creates/inspects only its
own never-started container using the actually supported
`up --no-start --no-deps --no-build --pull never --no-recreate`. Compose 5.7.0
does not support `create --no-deps`. Required flags are checked against actual
`up --help` before use. Original dependencies remain declared with safe stub
definitions; the successful created set must contain management only. Preserve command/entrypoint
null inheritance and every remaining field from actual Engine behavior. Prove
that declared published ports, bind mounts, resolved external network and exact
aliases match the fresh running service before reinserting those connectivity
fields. Image-declared volumes, unsupported options/fields and ambiguous
creation semantics reject. The observed shape is seven binds, no image/runtime
VOLUME declarations, one external bridge and three aliases including the repeated
`coolify`; an optional reviewed endpoint MAC pin must equal the exact existing
MAC. No new address, static IPAM or firewall acceptance is implied by this data.

Every other Config/HostConfig field remains from the actual probe, including all
63 observed HostConfig fields. The only proved start-state default transition
is Docker client/server 29.9.3, API 1.56, Linux/amd64: created
`OomKillDisable=false` becomes running `null`. With no explicit OOM option,
model only that exact transition before proposing the running contract. True,
missing/unknown defaults, explicit OOM settings or unknown runtime versions
reject; all other fields remain compared. Actual Docker client/server/context
metadata is captured and bound in every chain ticket. The current Compose 5.7.0
differs from the running instance's creator label 2.38.2; version/default changes
must appear in the review diff. Only eleven explicitly enumerated generated
Compose metadata fields may be projected from actual same-version config/hash/
version/path observations. The supported 5.7.0 explicit-name force-recreation
transition adds exactly `com.docker.compose.replace` equal to the observed old
name without its leading slash, **not** its old container ID. The old ID,
name/project/service and declared explicit name must all bind to actual inspect;
the replacement label appears in the proposed review diff and installed full
comparison. Unknown versions or transition metadata reject. Actual
`up --no-start --no-deps` supplies the dependency label semantics (empty on this
version); no invented dependency label is substituted. Structured dependency
label order alone is canonicalized, retaining every name/condition/restart bit.
Unknown generated keys reject; ordinary/image labels stay compared. Never
ignore a label prefix or assume the old creator version.

The runtime policy pins the observed Docker client `5457199` and server
`70efc0e` builds. The chain ticket also freezes the complete version response.
The exact binaries were exercised in a private Linux amd64 daemon with the
containerd image store. The fixture used cgroupfs. The target uses systemd
cgroups. The target still requires independently reviewed operator evidence
and a fresh contract capture before activation.

For the reviewed existing-MAC endpoint case, an empty requested `IPAMConfig`
may serialize as `null` or `{}`. Only these empty representations compare
equally; requested addresses remain compared and unknown IPAM keys reject.
The MAC itself stays in the contract and is never normalized away.

On the proved Docker 29 OCI image store, the container's immutable image/index
ID and `Config.Image` can differ from `com.docker.compose.image`, which records
the selected platform manifest. Derive its expected value independently with
actual `image inspect --platform linux/amd64` against that immutable index,
validate OCI descriptors/IDs and matching full Config/RootFS, and bind the
selected digest. The probe label is never its own authority. Wrong/unknown
platforms, descriptors, selected identities or runtime versions reject. Preserve
the original plan/container image ID; do not replace it with the label digest.

Environment is a sorted key→SHA256(value) map; duplicate/conflicting keys reject.
Binds, mounts, aliases and supported unordered multisets normalize order, while
command/argument and DNS order remain significant. Every other private string
leaf, including labels and commands, is also a SHA256 fingerprint. Reviewer
artifacts contain no plaintext credentials or whole environment lists. Changes
use individual key paths, including additions/removals with an explicit absent
marker. The independently approved difference manifest is `schema_version: 1`
with an exact list `changes: [{path, before, after}]`; no wildcard or automatic
approval. Raw observations remain only in fresh root-private operator state.

The plan's source hashes must come from the independently reviewed helper tree.
Its schema binds `project`, service `coolify`, ordered absolute `compose_files`,
absolute `env_file`, `expected_chain_ticket`, `running_container_id`, immutable
`candidate_image_id`, `probe_token`, exact three `tool_inputs` hashes, and an
explicit `action`. See the driver for the strict schema. Prepare a plan through
the trusted owner/reviewer and supply its **raw file SHA256 independently**:

```bash
helper_operator driver --tool-dir "${helper_tools_dir:?}" \
  --operator-manifest "${helper_binding_manifest:?}" \
  --expected-operator-manifest-sha256 "${helper_binding_sha256:?}" \
  --plan "${helper_operator_plan:?}" \
  --expected-plan-sha256 "${helper_operator_plan_sha256:?}" \
  --operator-state-dir "${helper_private_operator_state:?}" \
  --reviewed-changes "${helper_exact_changes:?}" \
  --expected-changes-sha256 "${helper_exact_changes_sha256:?}"
```

`prepare_review` needs no approved difference file and returns a **proposal**,
with `reviewed_diff_verified=false` and `activation_authorized=false`.
`probe_only` verifies the independently approved exact difference set and still
starts nothing. `activate_management` additionally requires both
`freeze_receipt_path` and `freeze_receipt_sha256` inside the independently
approved plan, plus deterministic reviewed endpoint identity. Non-activation
plans reject these receipt fields. Before **any runner call**, the driver
captures the exact canonical non-symlink receipt file directly inside the trusted
private operator-state directory. It must be a nonempty regular file, belong to
the effective operator, have no group/other permissions and be at most 1 MiB.
Its raw bytes must match the plan's independently approved SHA256; do not derive
a digest from the current file and call that approval, truncate or reserialize it.
The open is nonblocking and rejects nonregular types before reading; before/after
metadata must agree. The exact captured bytes are privately escrowed as
`verified-freeze-receipt.bin` with mode `0600`; identity evidence stays private.

Immediately after the final chain recheck, before the up marker/call, the same
path must yield identical bytes, device/inode, size, owner, mode, mtime and ctime.
Atime is excluded because reading can change it. Removal, replacement, changed
permissions or data drift blocks mutation. Only the actual verified SHA and
byte-integrity/recheck flags are reported, never receipt payloads/private paths.
This is **opaque byte integrity only**: there is no invented receipt schema or
machine verification of issuer, freshness, admission/drain or other runtime
semantics. Owner and MAIN must independently approve and maintain those gates;
`owner_runtime_gates_verified_by_this_tool` remains false. A matching stale
artifact does not establish fresh operational clearance.

The driver rechecks the **same actual apply chain/render/version** before
executing its one bounded management-only `up`. No alternate project/files or
caller arguments can be substituted into that operation. An exclusive owner
operation window/lock and absent concurrent mutators cover the check-to-exec
interval. A nonzero command does not retry. After success the same driver checks
the actual installed Engine contract, exact HTTP 200 without redirects, and the
chain again. It explicitly reports that runtime admission/drain/startup/staging
approval is **not** established by this tool.

Every Docker call uses the same controlled Compose client environment. Ambient
Compose flags are removed, known mutation/output flags are fixed explicitly,
and project `.env` Compose-control keys reject before observation. An inherited
`COMPOSE_REMOVE_ORPHANS` cannot silently broaden management-only activation.
Ordinary application values are preserved and compared. The private state
directory must belong to the effective operator, have mode `0700`, remain outside
Git, and have trusted non-writable ancestry; `/tmp` or a replaceable foreign-owned
parent is unsuitable. The outer activation timeout exceeds its 120-second wait.

The actual Engine health test must equal the official application test. A safe
probe establishes defaults/health plus the restricted proved projection; it is
never attached to production networks and never mounts production paths. Keep
the private recipe and raw evidence for recovery review; remove only its exact
owned never-started ID. Partial failure before an ID was assigned also discovers
the exact token/project/service subset; validate every member's image/name,
Created/PID0/zero StartedAt, network-none/no ports/no mounts before removing any.
Unexpected running state or ownership preserves the entire set for the operator.
Default Compose JSON escapes literal dollars;
preserve one encoding layer during replay and reject an unescaped dollar.
Never use `--no-interpolate`, invent health evidence or repeatedly decode until
it passes. Isolated fixtures must validate this same driver/Compose version and
its supported connectivity/metadata/dollar behavior before live use.

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
webhook settings. MAIN holds PR367, PR366, PR359 and other merges capable of native
auto-deployment. Merging this PR is not the repair: it triggers normal main
CI/CD/webhooks, and does not install the management derivative.

The owner must confirm a reviewed hold covering **all** deployment admission
sources: abby-loop and other merge producers, all control-plane automatic and
preview webhooks, hosted pipelines, manual/API/CLI operators and recurring
producers, including **already-running Sentinel agents and their push routes**.
Verify admission closure independently and show it persists across
management recreation, until explicit staging-only release. Maintenance mode
alone is insufficient: `webhooks/*` is exempt, and maintenance state may not
persist through initialization. Do not discard queued production work to make
the gate pass. If persistence cannot be proven, STOP and propose the additional
technical gate for separate review/approval; no blanket permission is implied.

Sentinel is a nonqueue producer: worker flags or a stopped Horizon do not stop
its HTTP pushes, controller heartbeat/cache writes or job admissions. Its
hostgateway/published-port endpoint can avoid Traefik; the actual endpoint,
port, routes and proposed fence coverage are UNVERIFIED, and this does not claim
bypass of every future boundary. Before relying on any empty samples, prove
producer absence/a durable nonqueue hold **or** obtain the finite reviewed
emission/admission-window and bounded-descendant proof in
[STARTUP_REVIEW.md A17–A18](STARTUP_REVIEW.md#recurring-sentinel-producer-and-acceptance-window).
Cover existing agents even if their startup check does nothing, and maintain
the selected proof through recreation, cache clear, worker release, staging and
recovery. This runbook authorizes no agent stop, push/heartbeat, flag, route,
fence, token or queue change.

Within that owner-approved hold, check HTTP 200 and fresh disk/runtime hashes,
stop scheduler/admission producers and close/drain nginx **and** PHP-FPM
gracefully. Prove no admitted request, keepalive/FPM child or independent CLI
producer remains. **Keep normal Horizon running with cache maintenance OFF**
while admitted work finishes; entering maintenance first would prevent normal
workers from draining. Check all
Redis ready/delayed/reserved/processing queues and every deployment, console
job, scheduled task and backup execution twice. A reserved cleanup job blocks
the gate just like other work; age is not completion. Do not acknowledge,
except, delete, requeue, reset attempts, kill jobs or clear queues to force a
pass. Abort and resume the old service if the gate cannot clear.

Only after all other work and queues genuinely drain, pause and stop Horizon gracefully with the reviewed
`/command/s6-svc -wD -T 30000 -O -t /run/service/horizon`. Prove its master,
supervisors and workers exited and repeat the empty/PID check. A timeout or
remaining executor blocks recreation. Only then enter actual cache maintenance
if required and verify literal startup holds for recreation. Recheck the owner hold, source binding,
image holders/escrow, disk/running snapshots, exact contract/recovery diffs and
host-port ownership. Record the complete private freeze receipt.

The added nginx/PHP-FPM s6 edges protect initialization only. Before recreation,
the owner must approve and verify **literal file** holds
`HORIZON_ENABLED=false` and `SCHEDULER_ENABLED=false` in the exact read-only
mounted `/var/www/html/.env`. The pinned native run scripts grep that file and
sleep on service startup. Process environment alone does not establish this
hold; verify actual image scripts, dependency graph, mount source/target/mode
and canonical file bytes, with no duplicate keys or ambiguous prefixes. The
public script SHA256s are `296dfda050b4d25c32fd9a858216a9a492148fd6ef9960644e08f32f7caf5e31`
for Horizon and `9034571c9f328e694720f9c66c461016e96a3d932ade29f5d2498754677d906c`
for scheduler-worker. Actual immutable-image verification remains required.
These holds do not drain current services; perform the genuine PRE-init drain
above first. Record exact controller-only file changes and restoration for both
candidate and recovery. Initialization does not create these file flags.

**Migration, seeding and the entire native startup closure are separate
pre-installation gates.** Follow the pinned-source branch/predicate/effects
matrix in [STARTUP_REVIEW.md](STARTUP_REVIEW.md) for both candidate and recovery.
All actual counts, targets and effects remain **UNVERIFIED**. The existing
36-file/predicate observer is incomplete and cannot certify these gates.
The pre-s6 debug branch can install development dependencies and run
optimize-clear. With the pinned Redis cache store, optimize-clear includes a
whole-effective-cache-database flush, not a prefix-only cleanup. Actual cache
bindings and any queue/Horizon database collisions are UNVERIFIED. Keep verified
backups/evidence before **any** startup or recovery; exit zero or HTTP health
does not prove every native branch completed successfully.
Native `db-migration` calls `migrate --force --isolated`; `MIGRATION_ENABLED`
defaults true. Require an independently verified **zero pending migration** set
for the exact image and actual database repository before recreation. Do not
invoke migration/pretend/status or a dry-run under a read-only assumption.

Next `init-seeder` runs forced `ProductionSeeder` on every enabled startup;
`SEEDER_ENABLED` defaults true. It rewrites localhost settings and conditionally
creates default rows, starts proxies and dispatches sentinel work. Its SSH
directory seeder unconditionally deletes/recreates persisted key/mux roots and
rewrites/chowns their contents; zero key rows do not remove that effect. OAuth
settings can be deleted in bulk when rows exist but authentik is absent. That
branch attempts to recreate a null provider against the pinned non-null schema,
fails after deletion and swallows the exception; successful restoration must
not be assumed. Actual schema/counts are UNVERIFIED. CA creation can delete
existing certificate rows, every server is a remote certificate-write target, and synchronous SSH
can happen before activity/job admission. Root-user, public-IP and other seeder
branches also write state or use external services. Nightwatch is a separate
longrun outside the Horizon/scheduler hold. Each source-defined conditional
target must be proven absent or separately reviewed; **unconditional and
persisted-host effects always require scoped review and verified backups before
installation**. Use the exact targets/counts/side effects and execution order in
the linked matrix, not only a class allowlist. Never skip native startup or
silently edit service flags to pass.

The explicit normal-create branch for still-missing StandaloneDocker 0 selects a
**synchronous** created hook that
inspects/creates the `coolify` network via SSH and runs
`ConnectProxyToNetworksJob::dispatchSync`. That job can delete mux state,
create destination-derived networks and connect the shared proxy. No Horizon
consumer is needed for those effects. Distinguish Server's quiet default
destination insertion, which does not run that hook, from the later explicit
create predicate. Prove that creation predicate absent, **or** independently
approve its ordered network/membership/host effects with verified restore
evidence **before installation**.

Queued `StartProxy` and `CheckAndStartSentinelJob` are not class-only harmless
startup admissions. Their execution can synchronously rewrite proxy Compose and
backup/prune files, change statuses, broadcast events and admit further tasks.
Proxy commands can pull images, stop/remove the shared proxy, start it with
orphan removal or deploy a stack, and reconnect networks. Completion listeners
can rewrite redirect/dynamic ingress, dispatch version checking or forcibly
remove a proxy found in Created state. Sentinel
work can fetch external versions, remove/recreate its container with Docker
socket and host-PID access, write persisted paths/settings and dispatch events.
Removal and invalid-token repair can precede endpoint validation, so a later
endpoint failure does not prove no mutation occurred.
Review their exact execution/descendant predicates, private targets/counts,
configuration/backup effects, privileges, events, ingress coverage and restore
plan **before installation and before any normal Horizon release**. All actual
targets/counts/effects remain UNVERIFIED. Worker holds do not defer inline
hooks; after release, normal workers provide no class selector or protection
from selected handler side effects. Shared-proxy changes can affect every
application using that host ingress,
so they are not a management-only or isolated-staging acceptance test.

After initialization the held services must be verified sleeping, with no
Horizon master/supervisor/worker or scheduler executor. **The native flags do
not suppress synchronous Init work.** Non-cloud Init calls
`cleanup:stucked-resources` after Redis/name cleanup and before failing execution
rows. That command can enqueue `CleanupHelperContainersJob` for functional
servers and high-priority `DeleteResourceJob` for trashed/orphaned resources.
`DeleteResourceJob` can stop applications/databases/services, remove volumes,
configuration and records, dispatch Docker cleanup, and enqueue another default
cleanup command wrapper. This closure is data-dependent and may recurse.
Other Init branches can enqueue high-priority `CoolifyTask` network-disconnect/
removal commands. Localhost-proxy compatibility can synchronously rewrite or
remove **TRAEFIK** `/data/coolify/proxy/dynamic/coolify.yaml`, changing management/
realtime/terminal ingress, as well as write/remove/reload Caddy configuration.
Direct cleanup also deletes empty teams, soft-deleted servers, orphan deployment
rows, trashed/orphan service children, scheduled tasks/backups and SSL records.
Template fetch/file writes, telemetry/public-IP calls, name/email/proxy rewrites
and restoring the trashed PostgreSQL 0 record followed conditionally by creating
**enabled daily scheduled-backup 0** are separate branches. Neither native
worker flag gates these actions.

Init also queues `PullChangelog` and `CheckHelperImageJob`; helper-error
notifications can create queued wrappers/channel send jobs and retries/delays.
Therefore neither an exact-two-job allowlist nor an unconditional bounded
housekeeping claim is valid. **Before installation or initialization**, obtain independently
reviewed aggregate branch-state predicates for the exact pinned Init/commands/
jobs, with resource and admission mutators closed. Prove destructive branches
and direct proxy/network mutations absent and the remaining actual startup
closure bounded, or obtain a separate scoped review of those exact mutations
**before installation**, not merely before releasing Horizon. Bind actual
DB/Redis database selection, prefixes, cache/lock clearing and all callsites/
arguments/payload hashes. A class-wide unique helper-cleanup lock can suppress
per-server admission, so dispatch-attempt counts are not accepted-job counts;
the broad helper selector must be proven safe when it actually runs after Init
has changed deployment statuses. Docker cleanup, queued command wrappers and
service-status broadcasts also belong to the conditional descendant review.
The native Redis cleanup deletes historical job hashes/lists/metrics and old
keys, deduplicates queues, clears matching stale overlap locks and marks selected
processing/reserved records failed. Empty executable queues do not prove those
other effects absent. Preserve and review the complete evidence/target set.
Do not invent count queries or assume job classes prove non-destructive behavior.
Preserve actual job identity/payload hashes privately and reconcile every branch.
Immediate post-init emptiness is not expected. Init's status/lock mutations are
also why the genuine PRE-init drain admits no exception. Never skip Init, patch
cleanup, insert jobs manually, invoke `queue_next`, filter/pop arbitrary work or
discard jobs to obtain a pass.

Keep the independently proven external admission gate and production producer
holds while the owner clears actual cache maintenance, then deliberately releases
normal Horizon only after that independent branch-state/closure review permits
natural completion of the exact observed startup work **and** A17–A18's recurring
producer/admission proof covers the release. Existing Sentinel can keep producing
even when CheckAndStartSentinelJob makes no change. Its first/null cached hash,
changed container state or effective force interval can admit PushServerUpdateJob;
cache flush can rearm that first-hash path. The job can synchronously execute
the full shared-proxy restart/configuration closure with `StartProxy::run(async:false)`
and create storage/resource/database-proxy/log-drain/status descendants. Review
those actual predicates, targets, counts and effects, not only a startup job list.
Normal workers require maintenance off. Scheduler remains disabled;
Horizon release is not a job-ID selector, so all competing producers/consumers
and delayed/retry sources must already be accounted for. Unexpected work blocks
release and requires review. Reconcile the known startup work and every emission,
direct write, admission and descendant in the independently reviewed hold/window,
then repeat the queue/execution checks within that proven scope before authorizing
the single staging request. **Two empty samples between pushes do not prove
quiescence or global drain.** A finite window supports only its explicitly
reviewed acceptance, not unbounded future admissions. Missing coverage, an
unjustified emission bound or an unexpected descendant is a STOP. Keep
application discovery disabled indefinitely until a new explicit
human instruction, including after hold restoration; no production deployment is a
startup or repair test.

Atomically install only the reviewed owned management override with immutable
candidate image ID, `pull_policy: never`, the application health test, and any
explicitly approved minimal reconciliation. Refuse concurrent/unknown changes.
Keep prior bytes and the separately prevalidated recovery override; preserve
every other service. After the independent operational gates clear, use only
the owner-approved `activate_management` plan through the chain-bound driver
above. It executes the same project/files as its observations, for service
`coolify` only, with `up -d --no-deps --no-build --pull never --force-recreate
--wait --wait-timeout 120`. Do not substitute a separate manual up command whose
files were not observed by that invocation.

Do not use `down`, `--remove-orphans`, installer, updater or a full-stack
recreation. On success verify Engine image/patch receipt/hashes, PHP 8.4.27,
actual health test and HTTP 200, private runtime/disk contract, unchanged other
workload identities and public application health. Recheck the updater hold,
all queues/executions and PID state immediately after initialization, while
external admission and native service holds remain effective. Reconcile and
complete only the expected bounded startup closure under the controlled normal
Horizon release above. Unexpected work blocks release; do not clear it or let
it become an unplanned production deployment.

Only then may the owner authorize admission of **one exact isolated staging
application/revision**, preserving its normal build secrets and helper restart
path, while every production producer remains held. Verify successful staging
and original-occupant preservation. Bind the existing staging branch to its
independently reviewed full commit through an owner-approved branch freeze/lock,
and verify remote HEAD before queueing and native resolution during the job.
The normal job resolves branch HEAD and can overwrite the row's commit; a
requested commit parameter alone does not establish the tested revision. Do not
create a new branch or alter protection under an implied permission. If safe selective admission cannot be
proven, leave the hold in place and STOP for a reviewed plan. After this proof
and every required gate passes, MAIN owns merge/release order **PR367 → PR366 →
PR359** and production release;
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

Read the durable `operation-status.json` under the reported private operation
state ID. It records distinct pre-mutation, up-running/up-failed,
post-up-contract-mismatch, http-failed and success stages. `up_executed` is
persisted before invoking management recreation, and `up_succeeded` only after
its successful return. Installed identity and private `post-up-inspect.json`
with its SHA256 are persisted **before** contract comparison. A successful,
HTTP-200 manager with a contract mismatch is a hold-and-inspect case; it does
not imply startup failure or authorize rollback. The error receipt/exception
preserves these facts rather than reporting every failure as pre-mutation.
Unknown identity/health remains explicitly unresolved. No stage automatically
retries, rolls back or releases admission holds.

If the final status write itself fails, the exception reports
`status-persistence-failed`, its `prior_stage`, `failed=true`, the error class
and `last_durable_state_current=false`, preserving known up/installed identity
evidence. The last durable file may be stale even if it says success. Keep the
hold and inspect privately; do not infer current success from that file or
automatically retry/rollback.

**Missing-manager recovery is a separate installation STOP.** The normal
chain/probe driver requires a live baseline and unchanged connectivity; it does
not implement recovery with a missing manager or the two additional base-image
startup-gate mounts below. Before any installation, require a separately
approved prevalidated recovery wrapper/packet binding the actual recovery file
chain, interpolated render, current Compose version/config hash, complete Engine
contract, immutable patched base, both nonsecret gate-file hashes/modes, and
fresh failed-state no-executor/queue/ownership proof. It must guard the actual
same recovery chain before one bounded recreation and HTTP 200 acceptance.
Until that wrapper/packet passes independent review, keep the external holds and
do not install. Do not substitute arbitrary saved Engine JSON, relax normal
guards, claim this driver covers missing-manager cases, or run a bare manual up.

The same admission, hash, drain, queue/PID and port gates apply to rollback.
Rollback starts the whole migration/seeder/Init closure again. Before **any**
rollback recreation, capture verified private failed-attempt evidence, including
Horizon records/lists/metrics that recovery's Redis cleanup can delete, then
obtain fresh failed-state predicates and scoped effects/backups for every branch
in [STARTUP_REVIEW.md](STARTUP_REVIEW.md). The first attempt can change the next
target set; do not reuse pre-attempt counts or assume rollback is only an inverse
image/test change. Unconditional persisted-host mutations still need review.
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
review the complete recovery contract with its image/test and extra gate mounts,
plus the full repeated native startup-effects packet. Do not reduce recovery
to an inverse image/test diff or infer no effects from preserved settings. Recheck
health dollar encoding/actual probe test. Do not restore the known-incompatible
6001 clause, drifted layout, mutable `${LATEST_IMAGE:-latest}` fallback, or an
unreviewed change. Prevalidate port ownership and a safe complete recovery
contract before the original instance is removed.

Atomically install the exact reviewed recovery override last in the preserved
file chain **only through that separately approved recovery wrapper**, recreating
only `coolify` with the bounded `--no-deps --no-build --pull never
--force-recreate --wait` procedure. If recovery itself
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

Operational validation is currently **unresolved**. Automatic security review
stopped live/network/service testing and installation on 2026-11-03, reporting
possible cybersecurity risk without a specific command. The owner subsequently
reported review/access resolution in the owning chat; that is **owner-reported
resolved**, not platform-verified restoration by this source task. No new
rejection or permanently blocked account is claimed. This lane remains local
source-only, and all installation/admission/startup/recovery/staging gates remain
held. Any separately authorized operation remains subject to ordinary controls;
a renewed rejection requires stopping, not rerouting through another tool,
model, account or connection. Local tests and source CI/review cannot establish
operational acceptance.
