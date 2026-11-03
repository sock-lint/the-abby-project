# Native startup and recovery review preconditions

This is a static review checklist for the official 4.1.3 source at
`c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2`, not a live inventory or an
executable observer. It records the additional scope of MAIN findings
`RV366G-RB1-A` and `RV366G-RB1-B`. **Every actual branch count, target set,
before/after value and proposed effect below is UNVERIFIED. Installation and
rollback remain blocked.** The older 36-file/predicate packet excludes
migration, seeder and other native branches and is not a complete startup audit.

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

| Branch / read-only predicate to establish | Expected targets/count and effects to review | STOP / required disposition before recreation |
| --- | --- | --- |
| A1. Native `db-migration` calls `start:migration`, which calls `migrate --force --isolated`; `MIGRATION_ENABLED` defaults true. Compare the image's exact ordered migration file names/hashes with the actual migration repository using an independently reviewed read-only plan. | **Zero pending migrations** and a consistent repository/schema are required. Record the full set and connection/lock bindings; the normal startup invocation still occurs. | Unknown/nonzero pending set or unverified connection/lock behavior blocks this repair for separate migration review. Do not invoke migration/pretend/status as a substitute for a proven read-only predicate. |
| A2. `init-seeder` invokes `ProductionSeeder` each start when enabled; `SEEDER_ENABLED` defaults true. Bind every selected default-row branch and the platform/environment conditions. | The source calls seeding once on that branch; actual invocation/effect counts are UNVERIFIED. Include all direct effects and dependent seeders. Missing default rows can create relationships and job admissions. | No assumption that an already initialized instance skips ProductionSeeder. Each row below must be independently reviewed. |
| A3. ProductionSeeder: Team 0 absent; User 0/Team 0 present with **no pivot for user_id 0**; settings/GithubApp/GitlabApp 0 absent; non-cloud Server/StandaloneDocker 0 absent; non-cloud non-Windows PrivateKey 0 absent with a selected persisted localhost-key file. | Count each exact conditional row/pivot/file selection separately and enumerate each insert/update/relationship/observer. Creating non-cloud Server 0 queues `StartProxy` and `CheckAndStartSentinelJob`; these admissions are unconditional **within that creation branch**. | Require zero selected missing-default branches or separate scoped creation/admission review. A total row count or only the exact team-0 pivot check does not reproduce these selectors. |
| A4. Localhost/server settings updated by ProductionSeeder; Windows Desktop branch updates or creates PrivateKey 0 with the public test key. | Exact localhost reachability/usability and setting writes; Windows predicate and key target/value fingerprint. Existing Server 0 is first set reachable/usable, then passed to CheckProxy; its pre-start false flags do not prove that call will skip. Sentinel dispatch uses `(metrics_enabled OR sentinel_enabled) AND not build-server`, not sentinel-enabled alone. | Writes cannot be described as absent merely because Server 0 exists. Review exact writes and subsequent predicates in order; any Windows-key branch requires separately scoped review and backup. |
| A5. `PopulateSshKeysDirectorySeeder` unconditionally deletes/recreates the `ssh-keys` and `ssh-mux` filesystem roots, then writes keys and recursively changes ownership; errors are swallowed. | Both roots, every selected private-key file and chown target. The disk names resolve to `storage/app/ssh/{keys,mux}`; the pinned upstream bind maps these to persisted host `/data/coolify/ssh/{keys,mux}`. Actual bindings still require proof. Directory deletion occurs even with zero key rows. | Mandatory exact host-path/entry/ownership review and verified SSH-state backup/restore before every recreation. Zero rows, unchanged key hashes or no error output do not remove this destructive branch. |
| A6. [OauthSettingSeeder, lines 30–63](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/OauthSettingSeeder.php#L30): settings count and existence of `authentik`; track each provider separately. | Existing settings with no authentik select deletion of **all** OAuth rows and attempted recreation, whose partial failure can be swallowed. Otherwise the ten configured providers each receive an update-or-create attempt; missing providers can be inserted. | Require the destructive predicate absent or separately approve all deletion/recreation effects and DB backup. The other branch still needs scoped target/observer review; do not assume its calls make no writes. |
| A7. `CaSslCertSeeder`: missing CA record per server, and its loop over **every Server**, without functional/enabled filtering. | Missing CA invokes SSL generation, including deletion of that server's certificate rows with null resource type/id before creating the CA. Every server remains a remote certificate-write target: directory creation, recursive SSL-directory chown/chmod, CA-file removal/rewrite and final file mode. `remote_process` attempts synchronous multiplexed-SSH setup/reuse before activity creation and high-priority `CoolifyTask` admission; a new ControlMaster is conditional. Record directory members, certificate-delete targets, connection attempts, activities and accepted jobs separately. | Review all servers/remote paths and SSL/SSH/DB backups before recreation. Existing CA records do not suppress the all-server rewrite loop. Worker flags do not prevent synchronous SSH. |
| A8. [SentinelSeeder, lines 13–25](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/SentinelSeeder.php#L13) and [ServerSetting, lines 189–229](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Models/ServerSetting.php#L189): empty token/custom URL fields. | Empty token generates and saves quietly; empty URL generates and saves quietly, using localhost, then FQDN, public IPv4, public IPv6 precedence. Only a still-empty generated URL selects `is_sentinel_enabled=false` and an ordinary save. Record each target/value fingerprint and subsequent job/observer effect separately. | Prove actual branch values/effects or obtain scoped review. Do not publish tokens or claim zero changes from total server count or sentinel-enabled alone. |
| A9. [RootUserSeeder, lines 18–73](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/database/seeders/RootUserSeeder.php#L18): User 0 absent and truthy effective `ROOT_USER_EMAIL`/`ROOT_USER_PASSWORD`, plus `ROOT_USERNAME`. | Exact prospective root-user/team relationship and registration-setting writes; DNS/password/HIBP validation can make external requests. Bind the actual dependency code before approving that behavior. | Prove the creation predicate absent or obtain separate root-bootstrap/security/egress review. Do not supply test credentials or silently change registration/inputs to pass. |
| A10. [CheckProxy, lines 19–104](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Actions/Proxy/CheckProxy.php#L19) and [configuration backfill, lines 25–43/98–108](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/app/Actions/Proxy/GetProxyConfiguration.php#L25). | `isFunctional=false` can delete the mux file; build-server with proxy clears proxy and saves. Then null/NONE/force-stop predicates may return; selected status checks synchronously use SSH and save status. Missing/invalid saved configuration can select mkdir/read/backfill/DB writes, default generation and dashboard cache writes, before downstream proxy-start admissions. | Review each ordered branch and exact server/proxy/config/cache/SSH targets even if no queue consumer starts. No read-only claim based on the method name, early-return expectation or worker hold. |
| A11. ProductionSeeder and Init each call [get_public_ips, lines 1749–1784](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/bootstrap/helpers/shared.php#L1749). | Bind both callsites, external `ifconfig.io` requests and InstanceSettings address updates, with expected values/egress privately reviewed. | An existing settings row does not eliminate unconditional invocation. Unknown request/write behavior blocks startup approval. |
| A12. Native [nightwatch-agent, lines 3–11](https://github.com/coollabsio/coolify/blob/c793d60e64e16e27ac0b8d7ee22d48b7c7622cf2/docker/production/etc/s6-overlay/s6-rc.d/nightwatch-agent/run#L3) greps the literal `.env` prefix `^NIGHTWATCH_ENABLED=true` without an end anchor. | Selected `nightwatch:agent` process, config/credentials and external effects/connections independent of Horizon/scheduler. Include prefix-matching/duplicate-line ambiguity in the file predicate. | Prove it is not selected or separately review/hold its exact native behavior through an owner-approved plan. Do not silently edit its flag or skip the service. |

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
| B1. Init runs optimize clear/optimize and calls template/changelog/helper methods before the non-cloud return. | Cache/file effects; CDN request and successful-response write under `templates/`; `PullChangelog` and `CheckHelperImageJob` admissions. Review retry/error and notification descendants. | All unconditional calls need scoped review and affected file/cache backups; no two-job-only startup assumption. |
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
hold restoration. MAIN owns merges and production release. Current operational
security review remains unresolved; this checklist grants no access or action.
