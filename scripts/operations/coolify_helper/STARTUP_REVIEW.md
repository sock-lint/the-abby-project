# Native startup and recovery review preconditions

This is a static review checklist for the official 4.1.3 source at
`c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2`, not a live inventory or an
executable observer. It records the additional scope of MAIN findings
`RV366G-RB1-A` and `RV366G-RB1-B`. **Every actual branch count, target set,
before/after value and proposed effect below is UNVERIFIED. Installation and
rollback remain blocked.** The older 36-file/predicate packet excludes
migration, seeder and other native branches and is not a complete startup audit.
MAIN's subsequent `34736af6` review identified two additional verified medium
subfindings under RV366G-RB1-A: `RB1A-H1` (StandaloneDocker created-hook inline
network effects) and `RB1A-H2` (proxy/Sentinel execution descendants). The same
omissions persist in the `f17932c3` matrix. Rows A13–A16 expand those specific
effects for renewed review; they do not report actual branch counts or clear
installation or worker release.
MAIN's final `09bc7fa2` disposition is NOT CLEAN with verified medium
`RV366J-H2-1`: the inline-network subfinding is fixed, but proxy/Sentinel scope
is partial because an **already-running Sentinel is a recurring nonqueue
producer**. Rows A17–A18 and the acceptance-window requirements below cover this
additional scope under the existing RV366G-RB1-A/H2 gate; mandatory IDs remain
twenty. Fresh review and actual evidence are still required.

The s6 sequence reaches database migration, then seeding, then `app:init`
before nginx/PHP-FPM become ready. Literal Horizon/scheduler holds prevent
their normal worker starts; they do not suppress this synchronous sequence,
SSH connections, writes, dispatches, model observers or other longruns.
Do not disable/skip migrations, seeders, Init or native cleanup to satisfy this
checklist. No dry-run command is authorized: the presence of a `--dry-run`
option does not establish that application boot or its dependencies are read-only.

## Required private packet before either recreation

An independent reviewer must approve a **separately scoped startup-effects and
recovery packet before installation**, while all competing mutators and
admission sources remain closed. For each individual branch in the tables,
record the following through a separately approved read-only observation plan:

- Exact image/source/file hashes, branch predicate and source callsite; effective
  literal startup flags; database/schema and Redis connection/database/prefix
  identities; filesystem mounts and canonical host paths. Do not infer an
  actual connection/database from a source comment or default.
- Exact selected IDs/paths, independently verified count, expected synchronous
  effects and queued/activity admissions; command/argument/payload hashes;
  model events/observers, recursive descendants, retry/delay/uniqueness behavior
  and failure/partial-completion paths. A table grouping never combines or
  excuses separate branch counts. Dispatch attempts are not accepted-job counts.
  Evaluate branches in native execution order against the reviewed effects of
  earlier writes; a predicate against only the pre-start snapshot can be wrong.
- Before-state hashes and independently verified private backups/restore steps
  for affected control DB, Redis/Horizon evidence, persisted SSH keys/mux state,
  SSL material, proxy configuration, templates and other written paths. Include
  ownership/modes and any host/remote targets. The native scripts' optional
  backups or swallowed exceptions do not establish this protection.
- A specific disposition: zero selected targets for a conditional destructive
  branch, **or** separately reviewed exact nonzero effects with bounded targets,
  backups and acceptance criteria. An unconditional operation cannot be made
  absent by reporting zero database rows. Such operations require their own
  scoped review and backups before recreation even when planned output equals
  current output.

Any missing source, uncertain selector/model scope, unknown target or count,
unbounded descendant, unexpected mutation or unreviewed effect is a **STOP**.
These predicates describe required evidence, not approved SQL or permission to
run Artisan, seeders, remote helpers or dry-runs. No such observer is implemented
or certified by this document. Keep raw values and credentials outside Git and
review artifacts; expose only approved counts and fingerprints.
Re-derive selectors from their stored fields without invoking application/model
methods: even `Server::isFunctional()` has a false path that deletes its SSH mux
file, so calling it is not a read-only predicate evaluation.

## A: migration, seeding and other native startup

The source entry points include the pinned
[migration command](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Console/Commands/Migration.php),
[seeder command](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Console/Commands/Seeder.php),
[ProductionSeeder](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/ProductionSeeder.php),
[SSH-directory seeder](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/PopulateSshKeysDirectorySeeder.php),
[CA seeder](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/CaSslCertSeeder.php)
and their complete callees. The selectors below must be evaluated against the
actual bindings and exact image files; actual results remain **UNVERIFIED**.
Numerals describing one invocation, provider lists or model lists below are
static source control flow/schema, not observed execution counts. **All actual
invocation, dispatch, accepted-job and effect counts remain UNVERIFIED.** A
required zero is an installation precondition, never a reported observation.

Matrix IDs group review topics; they are **not call order**. ProductionSeeder
processes defaults and localhost/CheckProxy/StandaloneDocker/Windows branches,
then public-IP lookup, OAuth, SSH population, Sentinel, root-user and CA seeders.
The same source order must drive the predicted post-write state and descendants.
`Server` uses SoftDeletes: a default-scoped `find(0)` can report absent for a
trashed row, while recreation can collide with its primary key and abort. Its
default chunks also exclude trashed servers. Prove exact row/scoping state,
including trashed IDs, rather than assuming absent means safe to create.

Successful process/oneshot exit or API health does not certify completion of
every native branch. Migration/Seeder call their child and explicitly exit zero
on normal return; this does not catch an exception. Their s6 scripts and
init-script use `foreground { ... }` with empty continuation: the documented
[foreground execution](https://skarnet.org/software/execline/foreground.html)
and [empty-continuation rule](https://www.skarnet.org/software/execline/grammar.html)
can also discard a nonzero child result. Actual installed execline/version
behavior remains UNVERIFIED. Uncaught failures can abort later Init operations;
caught errors can leave partial effects. The matrix is a possible ordered
closure, not a promise every row completes. Unknown completion or error
propagation is a STOP, not proof of safe emptiness.

| Branch / read-only predicate to establish | Expected targets/count and effects to review | STOP / required disposition before recreation |
| --- | --- | --- |
| A0. Pre-s6 [99-debug-mode.sh](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/docker/production/entrypoint.d/99-debug-mode.sh#L2) selects effective `APP_DEBUG=true`. | Composer installs development dependencies with no scripts, then invokes optimize-clear before the s6 chain. Review dependency/network/file and whole-cache effects described in B1; actual flag/targets/effects are UNVERIFIED. | Prove this branch absent or separately review exact effects and backups before **any** recreation. Do not silently change debug flags or treat the worker holds as an entrypoint hold. |
| A1. Native `db-migration` calls `start:migration`, which calls `migrate --force --isolated`; `MIGRATION_ENABLED` defaults true. Compare the image's exact ordered migration file names/hashes with the actual migration repository using an independently reviewed read-only plan. | **Zero pending migrations** and a consistent repository/schema are required. Record the full set and connection/lock bindings; the normal startup invocation still occurs. | Unknown/nonzero pending set or unverified connection/lock behavior blocks this repair for separate migration review. Do not invoke migration/pretend/status as a substitute for a proven read-only predicate. |
| A2. `init-seeder` invokes `ProductionSeeder` each start when enabled; `SEEDER_ENABLED` defaults true. Bind every selected default-row branch and the platform/environment conditions. | The source calls seeding once on that branch; actual invocation/effect counts are UNVERIFIED. Include all direct effects and dependent seeders. Missing default rows can create relationships and job admissions. | No assumption that an already initialized instance skips ProductionSeeder. Each row below must be independently reviewed. |
| A3. ProductionSeeder: Team 0 absent; User 0/Team 0 present with **no pivot for user_id 0**; settings/GithubApp/GitlabApp 0 absent; non-cloud Server/StandaloneDocker 0 absent; non-cloud non-Windows PrivateKey 0 absent with a selected persisted localhost-key file. | Count each exact conditional row/pivot/file selection separately and enumerate each insert/update/relationship/observer. Creating non-cloud Server 0 queues `StartProxy` and `CheckAndStartSentinelJob`; these admissions are unconditional **within that creation branch**. StandaloneDocker creation also runs the **inline** network effects in A13. | Require zero selected missing-default branches or separate scoped creation/admission review. A total row count or only the exact team-0 pivot check does not reproduce these selectors. Named proxy/Sentinel admissions require the full A14–A16 effect review. |
| A4. Localhost/server settings updated by ProductionSeeder; Windows Desktop branch updates or creates PrivateKey 0 with the public test key. | Exact localhost reachability/usability and setting writes; Windows predicate and key target/value fingerprint. Existing Server 0 is first set reachable/usable, then passed to CheckProxy; its pre-start false flags do not prove that call will skip. Sentinel dispatch uses `(metrics_enabled OR sentinel_enabled) AND not build-server`, not sentinel-enabled alone. | Writes cannot be described as absent merely because Server 0 exists. Review exact writes and subsequent predicates in order; any Windows-key branch requires separately scoped review and backup. |
| A5. `PopulateSshKeysDirectorySeeder` unconditionally deletes/recreates the `ssh-keys` and `ssh-mux` filesystem roots, then writes keys and recursively changes ownership; errors are swallowed. | Both roots, every selected private-key file and chown target. The disk names resolve to `storage/app/ssh/{keys,mux}`; the pinned upstream bind maps these to persisted host `/data/coolify/ssh/{keys,mux}`. Actual bindings still require proof. Directory deletion occurs even with zero key rows. | Mandatory exact host-path/entry/ownership review and verified SSH-state backup/restore before every recreation. Zero rows, unchanged key hashes or no error output do not remove this destructive branch. |
| A6. [OauthSettingSeeder, lines 30–68](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/OauthSettingSeeder.php#L30): settings count and existence of `authentik`; track each provider separately. | Only existing rows with **no authentik** select deletion of all OAuth rows. The recreation loop shadows the old row with a new model and assigns its still-null provider to itself. Against the [pinned non-null unique provider definition](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/migrations/2024_03_11_150013_create_oauth_settings.php#L17), the first save fails after deletion; the exception is swallowed and the later missing-provider loop is not reached. The other branch (no rows **or** authentik present) attempts update-or-create for ten providers and returns. Actual schema/counts/outcomes are UNVERIFIED. | Require the destructive predicate absent or separately approve exact deletion/failed-recreation effects and DB backup. Do not assume restoration succeeds or that every branch wipes settings. The update-or-create branch still needs scoped target/observer review. |
| A7. `CaSslCertSeeder`: missing CA record per server, and its loop over **every Server**, without functional/enabled filtering. | Missing CA invokes SSL generation, including deletion of that server's certificate rows with null resource type/id before creating the CA. Every server remains a remote certificate-write target: directory creation, recursive SSL-directory chown/chmod, CA-file removal/rewrite and final file mode. `remote_process` attempts synchronous multiplexed-SSH setup/reuse before activity creation and high-priority `CoolifyTask` admission; a new ControlMaster is conditional. Record directory members, certificate-delete targets, connection attempts, activities and accepted jobs separately. | Review all servers/remote paths and SSL/SSH/DB backups before recreation. Existing CA records do not suppress the all-server rewrite loop. Worker flags do not prevent synchronous SSH. |
| A8. [SentinelSeeder, lines 13–25](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/SentinelSeeder.php#L13) and [ServerSetting, lines 189–229](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Models/ServerSetting.php#L189): empty token/custom URL fields. | Empty token generates and saves quietly; empty URL generates and saves quietly, using localhost, then FQDN, public IPv4, public IPv6 precedence. Only a still-empty generated URL selects `is_sentinel_enabled=false` and an ordinary save. Record opaque private credential/target references and subsequent job/observer effects separately. | Prove actual branch values/effects or obtain scoped review. Do not hash/publish actual tokens or claim zero changes from total server count or sentinel-enabled alone. |
| A9. [RootUserSeeder, lines 18–73](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/RootUserSeeder.php#L18): User 0 absent and truthy effective `ROOT_USER_EMAIL`/`ROOT_USER_PASSWORD`, plus `ROOT_USERNAME`. | Exact prospective root-user/team relationship and registration-setting writes; DNS/password/HIBP validation can make external requests. Bind the actual dependency code before approving that behavior. | Prove the creation predicate absent or obtain separate root-bootstrap/security/egress review. Do not supply test credentials or silently change registration/inputs to pass. |
| A10. [CheckProxy, lines 19–104](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Actions/Proxy/CheckProxy.php#L19) and [configuration backfill, lines 25–43/98–108](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Actions/Proxy/GetProxyConfiguration.php#L25). | `isFunctional=false` can delete the mux file; build-server with proxy clears proxy and saves. Then null/NONE/force-stop predicates may return; selected status checks synchronously use SSH and save status. Missing/invalid saved configuration can select mkdir/read/backfill/DB writes, default generation and dashboard cache writes, before downstream proxy-start admissions. | Review each ordered branch and exact server/proxy/config/cache/SSH targets even if no queue consumer starts. No read-only claim based on the method name, early-return expectation or worker hold. |
| A11. ProductionSeeder and Init each call [get_public_ips, lines 1749–1784](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/bootstrap/helpers/shared.php#L1749). | Bind both callsites, external `ifconfig.io` requests and InstanceSettings address updates, with expected values/egress privately reviewed. | An existing settings row does not eliminate unconditional invocation. Unknown request/write behavior blocks startup approval. |
| A12. Native [nightwatch-agent, lines 3–11](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/docker/production/etc/s6-overlay/s6-rc.d/nightwatch-agent/run#L3) greps the literal `.env` prefix `^NIGHTWATCH_ENABLED=true` without an end anchor. | Selected `nightwatch:agent` process, config/credentials and external effects/connections independent of Horizon/scheduler. Include prefix-matching/duplicate-line ambiguity in the file predicate. | Prove it is not selected or separately review/hold its exact native behavior through an owner-approved plan. Do not silently edit its flag or skip the service. |
| A13. **RB1A-H1:** ProductionSeeder creates missing StandaloneDocker 0 in its self-hosted or Windows branch; bind the [created hook](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Models/StandaloneDocker.php#L25) and server/destination state **after** preceding seeder writes. | Before any functional guard, the hook synchronously uses SSH to inspect the selected network or create it with explicit overlay/attachable options, then calls [ConnectProxyToNetworksJob::dispatchSync](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Jobs/ConnectProxyToNetworksJob.php#L41). That inline job's functional guard can delete a mux file; its [network helper](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/bootstrap/helpers/proxy.php#L108) creates derived destination networks (swarm: overlay/attachable; non-swarm: attachable with no explicit driver) and connects `coolify-proxy`. Enumerate exact servers, network IDs/names/options, derived target set, existing memberships and connection/create/mux-delete effects. Actual counts are UNVERIFIED. | Prove the creation predicate absent, or separately approve all model-hook/inline network and SSH/filesystem effects with before-state/restore evidence **before installation**. Horizon/scheduler flags do not defer `dispatchSync`. A missing default row is not a database-only creation. Do not invoke the hook, `isFunctional` or network helper to obtain a read-only inventory. |
| A14. **RB1A-H2:** Each [StartProxy execution](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Actions/Proxy/StartProxy.php#L16), from A3/A4 or any other reviewed startup admission. Bind null/NONE/force-stop/build-server guard, async/force/restarting arguments, actual proxy type and swarm/development branch in execution order. | Once selected, it saves `starting` status, may broadcast UI change, resolves configuration and runs [SaveProxyConfiguration](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Actions/Proxy/SaveProxyConfiguration.php#L14). This saves full configuration/hash to the DB, then synchronously writes proxy Compose. A truthy differing old hash selects backup and pruning beyond ten retained files; absence of backup does not eliminate the Compose write. DB changes can precede SSH failure. Enumerate proxy paths/bytes, backup order/deletions, status/model/cache/broadcast effects and all synchronous SSH before remote-task admission. Actual effect/admission counts are UNVERIFIED. | Prove execution/selected effects absent or obtain separately scoped DB/config/backup/SSH/event review **before installation and before any normal Horizon release**. Pre-start flags may be overwritten by seeders. A queued StartProxy class or a `starting` status is not a bounded harmless housekeeping proof. |
| A15. **RB1A-H2:** StartProxy's selected remote branch and [ProxyStatusChanged listener](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Listeners/ProxyStatusChangedNotification.php#L17); bind exact configuration, image references, proxy identity, networks, event/listener arguments and status predicates. | Non-swarm commands can pull images, stop/remove `coolify-proxy`, create networks, run Compose up with `--wait --remove-orphans`, and connect networks; swarm uses stack deployment. Async mode admits a high-priority remote task after synchronous SSH/activity setup; sync mode runs inline. The queued after-commit listener probes/saves status; running selects redirect/dynamic ingress writes, force-stop reset, optional external Traefik-version fetch/job and UI broadcast; created selects synchronous forced shared-proxy removal. Enumerate every affected container/service/network, app route, file/cache/DB/event and recursive admission. Actual counts/outcomes are UNVERIFIED. | Shared-proxy operations can affect ingress across **all host applications using it**, beyond management/staging. Require exact separately reviewed effects, ingress continuity/hold proof and restore/backups before installation or worker release, or prove the branch absent. Worker flags alone cannot approve synchronous portions; normal worker release is not a job-class selector. No startup proxy restart/pull/orphan removal/stack deployment is authorized as a staging test. |
| A16. **RB1A-H2:** Each [CheckAndStartSentinelJob](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Jobs/CheckAndStartSentinelJob.php#L22) and [StartSentinel](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Actions/Server/StartSentinel.php#L13) descendant selected by A3/A4 or other startup work. Bind latest/running versions, both-zero/latest and older-version fallbacks, server eligibility and restart arguments. | Job execution fetches external version data and synchronously inspects/queries sentinel. StartSentinel skips swarm/build servers, but a selected restart calls StopSentinel **before** token/endpoint validation; a missing endpoint is not a no-removal predicate. It can remove/recreate `coolify-sentinel` with Docker socket, host PID and persisted `/data/coolify/sentinel` mount, then recursively chown/chmod that directory, enable/save settings, update heartbeat and dispatch an event. Bind the development custom-image/path branch, StopSentinel and all event descendants too. Enumerate image/registry/endpoint, container/mount/privilege/resource/command/DB targets and rollback state. Actual targets/counts/effects are UNVERIFIED. | Prove the entire execution/restart predicate absent or separately review exact agent/host/DB/event/egress effects and backups **before installation and before any normal Horizon release**. Existing `sentinel_enabled=false` alone does not prove no admission/restart. No sentinel removal/pull/start or socket/PID-host access is authorized by this checklist. |

For A13, distinguish the explicit `StandaloneDocker::create` with literal
network `coolify` and server 0 from Server's non-swarm created hook, which saves
its default destination **quietly** and therefore does not run the StandaloneDocker
created hook. The later missing-destination predicate must be evaluated after
that quiet insertion; an existing Server 0 with missing StandaloneDocker 0 is a
different branch. The connect helper uses its selected `networks` set, not all
possible networks: standalone/swarm destinations, running services/Compose apps
and previews, filtered/deduplicated with source-defined fallback. Enumerate that
exact set, including fallback `coolify` or `coolify-overlay`; do not widen it.

For A15, selected non-swarm startup also creates the dynamic directory and
truncates/writes `dynamic/Caddyfile` before image pull/recreation, including when
the selected proxy is Traefik. This is distinct from SaveProxyConfiguration's
Compose write and needs its own path/hash/backup/effect count.

For A16, StopSentinel removes the container and resets heartbeat; token
validation can regenerate and save quietly for empty, invalid **or undecryptable**
tokens before the endpoint guard. An endpoint failure can therefore follow both
removal and a token DB mutation. StartSentinel dispatches `SentinelRestarted`, a
broadcast event with a team-private channel when team ID exists; include exact
event arguments, channels and descendant/broadcast admissions. Do not expose
tokens or assume an endpoint failure means no effects occurred.

## Recurring Sentinel producer and acceptance window

This applies to agents that already run, independently of any startup job
starting/restarting an agent. A no-op CheckAndStartSentinelJob is not an absent
producer predicate. Horizon/scheduler holds do not stop external push requests,
synchronous controller heartbeat/cache writes or new job admissions.
Native request guards still apply: authentication/token, subscription,
functional-server and data-shape checks precede accepted-push heartbeat. The
functional false path can delete mux state; rejection/audit effects are not
proof of no writes. The pinned maintenance exemption lists webhooks and API
health, not this Sentinel route; a proven active maintenance hold can block
it, but cache clear or maintenance release cannot be assumed to preserve that
closure. Actual middleware/cache/route state remains UNVERIFIED.

Disabling metrics alone is not producer absence: StartSentinel's
`COLLECTOR_ENABLED` flag is distinct from its `PUSH_ENDPOINT` and
`PUSH_INTERVAL_SECONDS`. Existing agent state, behavior, configuration and
transport must be bound separately.

| Branch / read-only predicate to establish | Expected targets/count and effects to review | STOP / required disposition before acceptance |
| --- | --- | --- |
| A17. **RV366J-H2-1:** Every existing or startup-created Sentinel whose configured PUSH_ENDPOINT can reach management's [POST `/api/v1/sentinel/push`](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/routes/api.php#L208). Bind agent image/version/container/server, running state, endpoint/cadence, opaque private authentication reference and every actual route/admission path. | StartSentinel passes endpoint/host-gateway mapping; localhost URL generation uses `http://host.docker.internal:8000`, and pinned production Compose maps default host APP_PORT 8000 to management 8080. That path can avoid Traefik. After its native request guards, the [controller always updates accepted-push heartbeat synchronously](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Http/Controllers/Api/SentinelController.php#L93). Under a ten-second cache lock/block-five policy, a null/changed sorted name/state hash **or absent force key** selects admission; lock timeout skips it. Hash TTL is one day; force TTL defaults to 300 seconds, not the agent push cadence. Cache clear can rearm it. Count emissions/requests/direct writes/admissions separately; all actual bindings/counts are UNVERIFIED. | Prove this producer absent or durably held outside the queue across the operation, **or** obtain the finite-window proof below. Worker holds, enabled flag alone, startup-job list or two empty samples do not close it. Do not hash/print credentials or infer every future fence is bypassed: evaluate the exact hostgateway/published-port route against the proposed boundary. |
| A18. **RV366J-H2-1:** Every [PushServerUpdateJob](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Jobs/PushServerUpdateJob.php#L139) selected by A17, including force/first-hash cases when no agent restart occurs. Bind opaque callsite/data-shape references, effective queue connection, server/proxy/container state and descendants in execution order. | Per-server WithoutOverlapping expiry-30/dontRelease constrains execution; admission is not guaranteed execution or a concurrent restart. Storage cache/possible storage job runs **before** the empty-containers return. Resource/DB status/proxy/log-drain descendants remain possible. If proxy should run, was not found and CheckProxy selects start, [async:false StartProxy runs inline](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Jobs/PushServerUpdateJob.php#L669), including A14–A15 shared-proxy effects and team notification; the found-proxy branch can queue network connections under an effective cache interval (default 3600). Review Start/StopDatabaseProxy, ContainerRestarted, additional-server ComplexStatusCheck and StartLogDrain predicates. All targets/counts/outcomes are UNVERIFIED. | Prove selected mutation/descendant predicates absent or independently approve their exact bounded effects, targets, backups/restore evidence before installation, normal worker release, staging or recovery acceptance. Bind queued versus sync execution: worker holds do not prevent sync-connection handling; later queued execution still performs inline proxy effects. No raw request/job payloads or credentials belong in evidence. |

For A18, bind each actual descendant queue: StartDatabaseProxy uses deployment
queue selection (self-hosted high/cloud deployments), while StopDatabaseProxy
and StartLogDrain select high. Their action files do not establish a common
per-server overlap lock. ConnectProxyToNetworksJob has its own per-server
expiry-60/dontRelease lock; that is not the ten-second throttle suggested by its
comment. The periodic admission guard is the separate PushServerUpdate cache
key (default interval 3600). Do not turn these distinct locks/cache guards into
a guaranteed rate bound or shared serialization proof. Actual connections,
queue names, lock state, admissions and effects remain UNVERIFIED.

Before claiming a drain, bounded startup closure or staging/recovery acceptance,
independently approve and verify **one** of these concrete alternatives:

- A durable **nonqueue producer/admission hold**, or proven producer absence,
  covering every bound agent and push route through pre-drain, recreation,
  cache maintenance clear, normal worker release, staging and recovery. Bind
  existing agents as well as possible new starts and hostgateway/published-port
  paths; closure of a Traefik route alone is not this proof.
- An explicitly finite reviewed emission/admission observation window with
  trusted start/end, complete agent/endpoint/cadence coverage, a justified upper
  bound on emissions, requests, admitted jobs/retries and direct/recursive
  descendants, and reconciled actual counts and effects for that window.
  Use verified agent image/version and retry/cadence behavior; the controller's
  default 300-second force TTL is not a bound on agent emissions.
  Include first-push/cache-reset and effective force-interval behavior, in-flight
  requests, competing producers/consumers and the end boundary. Specify exactly
  what acceptance that window supports; do not extrapolate indefinite
  quiescence or silently release unreviewed future admissions outside it.

**Two empty queue/execution samples between pushes are not quiescence.** They
remain only snapshots inside the separately proven hold or reviewed finite
window. No sampled zero, startup job no-op, HTTP 200 or completed job class can
substitute for complete producer/admission and descendant accounting. Missing
coverage, an unjustified bound, unexpected push/admission/mutation or incomplete
reconciliation is a STOP with existing holds retained. This document authorizes
no heartbeat/push, agent stop, flag/token/route/fence change or queue operation;
any needed hold/change requires its own targeted owner-approved plan.

## B: Init, cleanup and direct proxy effects

Pinned source anchors:
[Init](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Console/Commands/Init.php),
[CleanupStuckedResources](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Console/Commands/CleanupStuckedResources.php),
[CleanupRedis](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Console/Commands/CleanupRedis.php),
[CleanupNames](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Console/Commands/CleanupNames.php)
and [Server proxy configuration](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Models/Server.php).
These entry points require their model observers/helpers/jobs to be reviewed
as part of the same closure, not only these files.

| Branch / read-only predicate to establish | Expected targets/count and effects to review | STOP / required disposition before recreation |
| --- | --- | --- |
| B1. Init runs optimize clear/optimize and calls template/changelog/helper methods before the non-cloud return. | Optimize-clear includes cache-clear. With the pinned Redis store, this flushes the **whole effective cache database**, independent of key prefix; actual driver/connection/database and collisions remain UNVERIFIED. Also review CDN request and successful-response template write, `PullChangelog`/`CheckHelperImageJob` admissions and notification/retry descendants. | All unconditional calls need scoped review and affected file/cache backups **before any startup/recovery**; no prefix-only or two-job-only assumption. |
| B2. Non-cloud Init loads all servers; `do_not_track == false` selects alive signal; `get_public_ips` is called separately. | Exact optional telemetry request and both public-IP callsites from A11; InstanceSettings writes. | Require the optional predicate absent or exact approved egress/effects; unconditional calls remain scoped. |
| B3. Environment name contains `/`; User email matches uppercase; server proxy type is `TRAEFIK_V2`. | Separate counts and IDs for slash-to-hyphen saves, email mutator rewrites and `TRAEFIK` proxy-type DB update. Include observers and uniqueness/collision effects. | Require zero selected rewrite targets or separate exact rewrite review/DB backup. |
| B4. Version-qualified `StandalonePostgresql 0` exists with soft-deleted state; scheduled backup 0 absent within that branch. | Restore the database record and possibly create an **enabled daily** backup 0. Enumerate DB/backup IDs, schedule and model descendants. | Require branch absent or separately reviewed restore/new recurring-admission effects. Never confuse this metadata restore with an application data restore. |
| B5. Functional servers whose proxy should run; unused-network difference and inspected endpoint membership select removal commands. | Exact servers/network IDs/endpoints and conditional disconnect/remove commands; synchronous inspections, activity and high-priority task admissions. | Require no removals or separate scoped network review with known targets. No broad empty-network or class-name assumption. |
| B6. `cleanup:redis --restart --clear-locks` runs using actual Horizon/default Redis bindings. | Completed/failed job hashes; recent/failed/completed lists, class/queue/process/supervisor/metrics/workload structures; timestamped keys older than seven days. Deduplication can delete/rebuild lists and remove empty redundant queue structures. | Independently enumerate exact keys/counts/TTLs privately and back up required history before recreation. Genuine empty executable queues do not imply no history deletion. |
| B7. Same Redis command: default-connection keys matching overlap with TTL -1; valid processing/reserved Horizon hashes with determinable start time under restart mode. | Lock deletion and processing/reserved status/failed-time/exception writes. Bind actual DB/prefixes; comments/defaults are not authority. | Require zero active executors/reservations and reviewed lock/history effects. Never use native cleanup to manufacture the pre-drain result. Malformed/skipped records and swallowed errors remain unresolved. |
| B8. `cleanup:names` visits all records of each of its 18 models; exact sanitizer changes `name`. | Separate selected IDs/counts per model: Project, Environment, Application, Service, Server, Team, eight standalone DB types, S3Storage, Tag, PrivateKey, ScheduledTask. It writes changed names without model events and appends a private change log. | Require zero differing names or separate exact rewrite/collision review and DB/log backup. Init supplies neither dry-run nor backup. Do not run either option under a read-only assumption. |
| B9. `cleanup:stucked-resources`: Team has zero members **and** zero servers; `Server::onlyTrashed`; deployment row's application relation is null. | Separate team deletions, all soft-deleted server force-deletions, and orphan deployment-row deletions, including model events/descendants. | Require each selector empty or separately reviewed exact deletions with backups. Existing empty teams are not implicitly disposable. |
| B10. Same cleanup: `ServiceApplication`/`ServiceDatabase` is trashed, or its service relation is absent. | Each selection is a direct `forceDelete`, not merely a queued worker operation. Count trashed and orphan branches separately, including overlap and observers. | Require zero targets or scoped direct deletion review before installation; held Horizon does not protect these records. |
| B11. Same cleanup: ScheduledTask lacks both service and application; ScheduledDatabaseBackup cannot resolve a server; SSL certificate `server_id NOT IN (SELECT id FROM servers)`. | Direct scheduled-task, backup and certificate deletions; the raw servers subquery includes soft-deleted rows. Preserve exact relationship scopes and SQL NOT IN/NULL behavior. A naive null/left-join orphan check is not the source selector. | Require zero selected targets or separate reviewed deletion effects/DB backup. A failure resolving a backup server is not automatically a clean zero count. |
| B12. Same cleanup: functional servers for helper cleanup; trashed Application/Preview/Service/eight standalone database types; orphan previews/applications/services and only the five source-selected live database types (PostgreSQL except ID 0, Redis, MongoDB, MySQL, MariaDB), using their exact environment/destination/server predicates. | Default helper-cleanup dispatch attempts and conditional high `DeleteResourceJob` attempts. A source `destination()` call's truthiness is not equivalent to an absent relation/FK; independently derive the exact method and relationship scopes without invoking it. Audit each selector, source-specific ID-0 exclusions, overlaps, class-wide unique locks and active-deployment exemptions evaluated **when jobs run**. Evaluate downstream candidates after earlier direct mutations/observer effects, not independent zero snapshots alone. | Require destructive selectors empty or scoped exact resource effects. Accepted jobs may differ from attempts. Review DeleteResource descendants: stop/remove resource data/config/volumes, Docker cleanup, queued command recursion and service-status broadcasts. |
| B13. Deployment statuses QUEUED/IN_PROGRESS; ScheduledTaskExecution/BackupExecution status running. | Native bulk writes mark them failed, add messages/times for executions. | Genuine pre-drain requires **zero** such active records before Init. Do not treat startup's forced failures as successful completion. |
| B14. Localhost server 0 reaches `setupDynamicProxyConfiguration`; branch on actual proxy type, FQDN, cloud/local predicate and scheme. | **TRAEFIK** writes/removes `/data/coolify/proxy/dynamic/coolify.yaml` via synchronous SSH and can change dashboard/realtime/terminal ingress. Caddy writes/removes its dynamic config and reloads. Bind exact resolved paths/config hashes/routes in both branches. | Mandatory exact proxy-effect review and backup before recreation, or prove the callsite/selected type absent. Do not claim direct startup effects apply only to Caddy or that ingress closure survives a regenerated route without proof. |
| B15. Effective `constants.coolify.autoupdate` is non-null. | Init writes DB auto-update true/false according to actual effective value. | Require the separately verified startup false/DB false policy and exact intended DB write. A pinned image does not prevent updater/config mutation. |

For B1, the pinned framework
[OptimizeClear command](https://github.com/laravel/framework/blob/b8b55ce32175cc00f834a56eeb6316f18ed6ea39/src/Illuminate/Foundation/Console/OptimizeClearCommand.php#L59)
includes cache-clear, whose RedisStore
[flush method](https://github.com/laravel/framework/blob/b8b55ce32175cc00f834a56eeb6316f18ed6ea39/src/Illuminate/Cache/RedisStore.php#L282)
uses database-wide FLUSHDB. Bind the installed dependency bytes, effective cache
driver/connection/database and any queue/Horizon/shared-data collision before
reviewing its effects. Source defaults for separate database numbers do not
prove current separation. The existing requirement to back up evidence
**before any candidate or recovery startup** remains; do not reverse that order
or claim the earlier runbook captured evidence only after cleanup.

For B9, Team's normal servers relation excludes soft-deleted servers, so its
zero-server predicate is not a raw all-rows count. Deletion can cascade through
notification children, token/key revocation, source reassignment/deletion, tags,
shared variables and S3 records. PrivateKey deletion can delete persisted key
files, while its save paths can validate/throw, rewrite key files and refresh
connections. Bind each actual cascade/target and partial-failure path; do not
invoke model hooks to derive a read-only predicate. All actual counts remain
UNVERIFIED.

For B12, the trashed PostgreSQL selection includes ID 0; only its live-orphan
loop excludes ID 0. DeleteResourceJob's `finally` can force-delete the record
after earlier cleanup failed, then conditionally request Docker cleanup and
queue more cleanup work. A failure inside `finally` can prevent later steps;
neither an earlier exception nor a named job class proves no deletion or complete
descendant execution. Independently reconcile the exact partial effects before
release or recovery.

## Recovery is another full startup, not an inverse image change

The original patched base and the derivative both execute the native migration,
seeder and Init closure. A recovery image or validated s6 graph alone does not
approve those effects. Recompute the entire packet against **fresh failed-state
predicates** before any rollback/recreation: a partial attempt can change the
next selected targets, migrate/create/delete rows, rewrite host paths, queue
descendants or alter proxy ingress. Recheck the same DB/Redis/file bindings and
complete before/after effect set, including unconditional operations. A missing
manager does not imply a drained or unchanged instance.

Before any recovery start, capture the failed attempt's operator status, exact
container/inspect identities, timestamps, private logs, DB execution/job records,
Horizon job hashes/lists/metrics, payload fingerprints, lock state and relevant
file/config hashes into verified private escrow. In particular,
`cleanup:redis` on the recovery startup can delete completed/failed Horizon
records and lists from the failed attempt and can mark remaining work failed.
Capture this evidence **before** native cleanup can erase or rewrite it.
Unknown or incomplete evidence, new destructive targets, active work or missing
fresh scoped review is a STOP; keep external admission closed. No blind retry,
queue clear/pop, reservation exception, vendor startup bypass or automatic
rollback is authorized.

The missing-manager recovery wrapper remains separately unimplemented and
unapproved. All source, runtime, admission, recovery and staging gates in the
[main runbook](README.md) still apply. Discovery remains disabled indefinitely
until a new explicit human instruction, including after any approved repair or
hold restoration. MAIN owns merges and production release. The owner reports
review/access resolution; platform restoration has not been independently
verified by this source task. All installation/startup/recovery/staging gates
remain held, and this checklist grants no access or action.
