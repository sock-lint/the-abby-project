# apps/printing/

The Forge — 3D print requests. A child asks for a model to be printed; a parent
approves it against a monthly filament + print-time budget; the parent slices
and prints normally from Bambu Studio or Handy; a single MQTT listener notices
the print, links it to the request **deterministically**, tracks it to FINISH or
FAILED, and debits the budget. Frontend lives at `/quests?tab=forge`.

## The one idea worth understanding

**Matching is an equality check, not a guess.** On approval the app mints a slug
that embeds the request's primary key (`req-0042-dragon`) and tells the parent
to save the sliced plate as `req-0042-dragon.3mf`. Bambu firmware reports that
name back as `print.subtask_name`, so linking a job to a request is
`normalize_subtask_name(reported) == request.slug`. Nothing is scored, nothing is
fuzzy, and nobody hand-links anything. `PrintJobViewSet.link` exists purely as a
fallback for a plate someone started from Handy without renaming it.

## Models
- `PrinterProfile` — one physical printer. **Per-family content** (`family` FK,
  same shape as `Reward` / `Chore` / `ProjectTemplate`), non-null from
  `0001_initial` because there are no legacy rows. Credentials (LAN access code,
  or Bambu cloud uid + token) live in `encrypted_secret` as a Fernet blob via
  `set_secrets()` / `get_secrets()` — never in cleartext columns, never
  serialized out. `transport` is `local` | `cloud`.
  **`missing_credentials` is the primitive**, not `has_credentials`: it returns
  the *write-serializer field names* still blank for this transport (`host` +
  `access_code` for LAN, `cloud_user_id` + `cloud_token` for cloud), which is
  what lets the API hang a 400 on the exact input and the card say which field
  to fill. `has_credentials` and `credential_hint` (one human sentence) both
  derive from it, so the API, the parent UI and the supervisor's skip-reason
  can't disagree. `PrinterProfileWriteSerializer.validate()` refuses an
  incomplete printer outright — a saved-but-undialable printer is the failure
  mode this subsystem is worst at explaining, so it never gets created. That
  check needs `instance=` on PATCH to see the stored secrets; without it a
  rename-only PATCH reads as a create with no access code and 400s.
  **Where the access code lives is one string**, `constants.ACCESS_CODE_LOCATION`,
  read by the model hint, the serializer's validation error, the LAN transport's
  connect error and the form's help text. Four hand-written copies once shipped
  `Settings → Network`, a menu X1 firmware does not have; the code is inside the
  **LAN Only** panel, readable with the toggle still off — and it must stay off,
  since switching LAN Only on is what severs Handy/cloud access while buying us
  nothing (the local broker publishes status in Cloud mode either way).
  `AccessCodeLocationTests` pins all four surfaces to the constant.
- `PrintRequest` — the ask. `ApprovalWorkflowModel` + `TimestampedModel`.
  `slug` carries a **partial** unique constraint (`~Q(slug="")`) because many
  pending rows sit at `""` before approval. `estimated_grams` is what the budget
  debits — see "Where grams come from" below.
- `PrintBudget` — 1:1 with a child. `grams_per_month` / `minutes_per_month` are
  **nullable**, and null means *no cap* (zero is a real value meaning "nothing
  this month"). `is_active=False` ledgers everything but enforces nothing.
- `PrintBudgetLedger` — append-only, **two dimensions** (`grams` + `minutes`).
  Deliberately not a `BaseLedgerService` subclass: that base assumes a single
  `amount` column, and splitting into two single-amount ledgers would double
  every write and make one print's two debits reconcilable only by timestamp.
  `period_month` is denormalised so the monthly rollup is an indexed equality
  filter rather than a timezone-sensitive range scan.
- `PrintJob` — one observed print. `user` is denormalised from `request.user` so
  queryset scoping is one join; an unmatched job has `user=None` and is visible
  to parents only. A partial unique constraint enforces **one open job per
  printer** — the X1 prints one plate at a time, so a second open row means we
  failed to close the first. `gcode_start_time` is the *print run's* identity
  as the printer sees it, and it is stored for exactly one reason: it is what
  a restarted listener matches on to re-attach to this row. See "Surviving a
  restart".
- `PrintJobEvent` — the timeline. Append-only. This is the surface where a
  decoded HMS message replaces a raw code.

## Status machines
`PrintRequest`: `pending` → `approved` | `rejected`; `approved` → `printing` →
`completed` | `failed`; `pending`/`approved` → `cancelled`. A **cancelled print**
(stopped on the printer) sends the request back to `approved`, not `failed` — the
plate is still named, so a re-slice re-binds to the same slug.
`BINDABLE_STATUSES` (what a job may attach to) is approved / printing / failed /
completed; rejected and cancelled requests can never absorb a print.

`PrintJob`: `running` ⇄ `paused` → `finished` | `failed` | `cancelled` | `unknown`.
`unknown` means the printer stopped reporting — we don't claim it succeeded.

## The MQTT layer
- `transports/base.py` — `PrinterTransport` ABC + `PahoTransportBase` (paho-mqtt
  **2.x**: `CallbackAPIVersion.VERSION2`, five-arg `on_disconnect`, a random
  client id per process, `reconnect_delay_set(1, 30)`).
- `transports/local.py` — the printer's own broker. `bblp` / LAN access code,
  port 8883. **`check_hostname=False` always**: the certificate's CN is the
  printer *serial*, not the IP you dial, so a hostname check can never pass. With
  `PRINT_BAMBU_CA_CERT` set the chain is still verified. TLS is capped at 1.2
  because some firmware never answers a 1.3 ClientHello, and
  `VERIFY_X509_STRICT` is cleared because Bambu's CA omits `keyUsage`.
- `transports/cloud.py` — `us.mqtt.bambulab.com:8883`, username `u_<uid>`,
  password = the account `accessToken`. TLS verifies **normally** here (DigiCert,
  CN matches) — do not copy the local transport's relaxed policy.
- `transports/memory.py` — `InMemoryTransport`. No network. Tests and
  `run_printer_listener --replay` drive the real ingest path through it.
- `transports/__init__.py` — `build_transport(printer, …)`. Swapping local↔cloud
  is a value change on `PrinterProfile.transport`; no calling code changes.

## Exactly one connection
The X1's embedded broker accepts roughly **four** MQTT clients. Bambu Studio,
Handy, and Home Assistant each hold one, so a per-worker connection blows the
ceiling and the broker starts silently dropping clients — you and Home Assistant
end up kicking each other off in a loop. Two enforcement layers:

1. **Structural** — the listener runs only in its own `run_printer_listener`
   process (compose service `printer_listener`). Gunicorn and Celery never import
   a transport. This is the guarantee that actually holds.
2. **Runtime** — `PrinterLock`, a Redis advisory lock per serial with a TTL,
   refreshed by the supervisor. Scale the service to two replicas and the loser
   skips the printer instead of joining the fight.

Everyone else reads state through `fanout.py`: a cache snapshot (what
`GET /api/printers/<id>/status/` serves), a Redis pub/sub channel, and an
optional MQTT republish to `PRINT_FANOUT_MQTT_URL` under
`abby/printers/<serial>/state`. **Point Home Assistant at that** instead of at
the printer.

## Reports are deltas
The single most common source of wrong code against this protocol. A routine
`msg: 1` payload contains only the keys that changed; a legitimate report can be
`{"print": {"layer_num": 10, "command": "push_status", "msg": 1}}`. The merge
rule in `report.py` is `state.field = data.get("field", state.field)` — **never**
`data.get("field", 0)`. `msg: 0` marks a full snapshot, which is what `pushall`
returns and what seeds state; nothing is persisted until `state.seeded` is True.

Other traps `report.py` and `jobs.py` handle, each of which has bitten someone:
- Command acknowledgements carry a `print` key too — ingest gates on
  `command == "push_status"`.
- The cloud broker sends `{"event": {...}}` envelopes with **no** `print` key.
- `mc_percent` can still read 100 from the previous job at the instant a new one
  starts, so job bracketing uses `gcode_state` transitions and nothing else.
- `mc_remaining_time` is **minutes**, not seconds.
- Types are unstable across firmware: `task_id`/`gcode_start_time` are strings,
  `layer_num`/`mc_percent` are ints, `mc_print_stage` is a string holding a
  number. Everything goes through `_as_int` / `_as_str`.
- `print_type == "system"` is calibration gcode, not a user's print.
- `hms: []` in a delta genuinely means "all clear" — that field IS re-sent.
- `ams_mapping` is sent **once**, at print start, and is not in the snapshot.

## Reading the AMS

`filament.py` turns the `ams` block into the list the UI picks from, and it is
the one module that knows that payload's shape — the same division `hms.py`
has. Two things it exists to get right:

**Nesting breaks the delta rule.** "Keep the previous value when the key is
absent" is a rule about *keys*, and it cannot reach inside `ams`. Assigning
`state.ams = block["ams"]` looks like the same rule and silently blanks every
bay a partial delta didn't mention. `merge_ams` merges by unit id and tray id
instead: a full block merges to itself, a partial one keeps what it didn't
mention, and knowledge only accumulates. Deciding what is *currently* in a bay
is `describe_trays`' job, on the state of the moment — which is also how a
spool **removal** works, since firmware reports it as the tray with its fields
blanked rather than as an absent entry.

**Most fields are optional, and the honest answer is often "we don't know."**
Every uncertain value is `None`, never a plausible-looking zero:
- `remain` comes off an RFID tag, so **third-party spools have no percentage**
  and report `-1`. The UI renders no number rather than "0% left" on a full
  roll.
- `tray_color` is RGB**A**. Alpha `00` means unread or empty — which is *not*
  `000000FF`, real black filament, so the alpha check comes before any
  "is it all zeroes" instinct. A null colour renders as a dashed outline.
- `tray_weight` is the spool's **nominal** weight and is deliberately not
  surfaced: it reads as a quantity and is wrong every time. Consumed filament
  is still not in this payload — see "Where grams come from".
- `vt_tray` is the external spool holder, a *sibling* of `ams`, and on a
  printer with no AMS it is the only filament path there is.

`tray_exist_bits` would be a second opinion on which bays are occupied, but its
bit ordering across multiple units is unverified against hardware and
`describe_trays` already answers from the tray's own fields. We don't guess at
a bitfield to duplicate an answer we already have.

The snapshot carries `filaments: [{slot, material, label, display_name, hex,
remain_percent, is_external, filament_id}]`, so it reaches the SPA through
`GET /api/printers/<id>/status/` like everything else — no second connection.
`live_status` is `IsAuthenticated`, not parent-only, which is what lets a
child's request form show the picker. Filament is shared-hardware fact, not
identity, so unlike `subtask_name` it is not redacted for a sibling.

## Surviving a restart

`PrinterJobTracker.open_job_id` is in-memory state, and the process holding it
restarts on every deploy. A print runs for hours, so **a restart lands
mid-print routinely** — this is the normal case, not an edge case. The tracker
therefore does not trust its own empty memory: on the first seeded report
`_resume` asks the database whether this printer already has an open job for
the print it is now watching, and re-attaches to it (`_adopt`), restoring the
open job id, the last persisted percent, the last `gcode_state` and the set of
HMS codes already on that timeline.

Skipping that step is what "prints are being duplicated" looks like from the
Forge: the restarted tracker sees "printing, named, and no open job", writes a
**second** row for one plate, `_force_close_stale` closes the first as
`unknown`, and the parent gets a pair of rows in "Prints without a request"
for a single print. On a *linked* print it is also an accounting bug —
`close_out` debits the abandoned row as a partial failure and then debits the
new one the full estimate, and `request.print_count` counts one plate twice.

Identity is `_is_same_print`, three rungs, strongest first, and the first rung
both sides can answer settles it **in both directions** — a mismatch is a real
"no", not a fall-through to something weaker:

1. `gcode_start_time` — the printer's own id for the run, present in the
   pushall snapshot, so it survives our restart. This is the rung that
   normally decides.
2. `task_id` — only meaningful for cloud-started prints; a LAN start reports
   `"0"`. Both `"0"` and `""` mean *no id*, not *id zero*, which is what
   `_print_identity` exists to say.
3. The normalised name, and only for a row the printer was still reporting on
   within `STALE_JOB_MINUTES`. This rung covers rows written before
   `gcode_start_time` existed (adopting one backfills it) and firmware that
   reports neither id. The freshness bound is what stops a re-print of the
   same plate from absorbing a row a power cut left open.

Adopting also fixes the reverse case: reconnecting to a printer already
sitting in `FINISH` closes the row **as finished** on that first report,
instead of leaving it for `reconcile_stale_jobs` to write off as `unknown`
hours later with a partial-failure debit.

## HMS decoding
`hms.py` + `hms_codes.py`. Two namespaces, two encodings, **do not mix them**:
- `hms` is `[{attr, code}]`. Canonical string is four hex groups
  (`attr>>16 _ attr&0xFFFF _ code>>16 _ code&0xFFFF`). Group 3 is severity
  (1 fatal / 2 serious / 3 common / 4 info); the high byte of group 1 is module.
- `print_error` is one 32-bit int rendered as **two** groups (`0300_400C`)
  against a completely different table (`device_error`, ~950 entries, essentially
  disjoint from the ~5000 `device_hms` entries). Its module byte is the same
  space; **its severity is not** — any non-zero value means the print stopped.
  It latches for only a couple of seconds, so `PrinterJobTracker` captures it on
  the rising edge rather than polling.
- `0x0300400C` (decimal 50348044) is a **normal user cancel**, not a crash.
- A table miss is normalised (AMS unit byte, slot nibble) and retried before we
  give up — one vendored entry answers for every unit/slot permutation. Even a
  total miss renders severity + module, never a bare "unknown error".

To extend the table: add rows to `HMS_MESSAGES` in `hms_codes.py`. Bambu
publishes the full set at `https://e.bambulab.com/query.php?lang=en&d=<serial-prefix>`
— vendor from it offline, never call it at request time.

## Where grams come from
**The MQTT report does not carry consumed filament.** There is no such field;
every `weight` in the payload is a spool's nominal weight. So grams are
*estimated* by the parent from the slicer at approval time
(`PrintRequest.estimated_grams`) and that is what the budget debits. Minutes, by
contrast, are observed — we debit the job's real wall-clock duration. A failed or
cancelled print is debited proportionally to layers completed, floored at
`FAILED_PRINT_MIN_FRACTION` (a print that dies on layer 1 still burned a purge
line and a skirt) and floored again when the layer count is unknown. The other
routes to a real number — FTP'ing the `.3mf` and parsing
`Metadata/slice_info.config`, or the Bambu Cloud task API — are also slicer
estimates, so they would add a dependency without adding truth.

## Services
- `PrintRequestService` — `create_request`, `approve` (mints the slug, **only
  place that writes it**), `reject`, `cancel`, `link_job` / `unlink_job` (the
  manual fallback; both refuse a job that has already been debited),
  `close_out` (idempotent — a duplicate FINISH on reconnect can't double-debit).
- `PrintBudgetService` — `get_usage` / `get_remaining` / `summary` /
  `check_affordable` / `record` / `grams_for_failed_print` / `is_low`. Months are
  `America/Phoenix` local via `timezone.localdate()`, so a print finishing at 6pm
  on the 31st doesn't get billed to next month.
- `PrinterJobTracker` (`jobs.py`) — the edge detector. Writes only on meaningful
  transitions: at ~1 report/second, persisting every message would be ~86,000
  writes per printer per day. Progress rows are throttled to 5% steps and the job
  row is updated only when the integer percentage moves; live layer counts and
  ETA reach the UI through the Redis snapshot instead.

## Constants (`constants.py`)
`SLUG_PREFIX="req"`, `SLUG_ID_WIDTH=4`, `SLUG_TITLE_MAX=40`,
`PLATE_EXTENSION=".3mf"`, `STRIPPABLE_EXTENSIONS` (longest-first),
`FAILED_PRINT_MIN_FRACTION=0.1`, `STALE_JOB_MINUTES=180`,
`PROGRESS_EVENT_STEP_PERCENT=5`. Budget warn threshold is
`budget.LOW_BUDGET_FRACTION=0.2`.

## Exceptions
`PrintRequestError`, `BudgetExceededError` (carries `.problems`),
`TransportError`, `TransportAuthError`, `UnsafeURLError` (from `config.url_safety`).

## Settings
`PRINT_BAMBU_CA_CERT`, `PRINT_BAMBU_CLOUD_HOST`, `PRINT_BAMBU_CLOUD_PORT`,
`PRINT_FANOUT_MQTT_URL`. Beat: `print-reconcile-stale-jobs` at 00:35.

## Key entry points
- `matching.py` — the deterministic-linking contract.
- `jobs.py::PrinterJobTracker.handle` — one merged report in, rows out.
- `listener.py::ListenerSupervisor` — owns the connections and the locks.
- `filament.py` — the AMS payload's shape, and what we will claim from it.
- `management/commands/run_printer_listener.py` — the only process that connects.
  `--capture <dir>` records what the printer actually said (one
  `<serial>.jsonl` of raw payloads per printer, written on the consumer thread
  so paho's never touches the filesystem); `--replay <file> --serial <s>`
  pushes it back through the real pipeline with no network. Together they are
  how you debug "why didn't this link" — or write a parser against firmware
  you don't have in front of you.
- `apps/printing/tests/test_ingest.py` — end-to-end ingest with no broker.

## Deploying it

Production is deployed by **Coolify as a Compose resource** (confirmed with the
operator; see the README's "Deployment (Coolify)" section) — *not* by the
GitHub Actions pipeline, which SSHes to a different host and whose runner has
been offline for months. Because it is a Compose resource, Coolify brings up
every service in `docker-compose.yml`, so `printer_listener` needs no extra
registration to start. Two things still do not live in this repo: Coolify's
configuration is in Coolify's own database, and the Actions pipeline enumerates
services by hand (`.deploy.yml` → `app_services`, and the `for svc in …` loops)
— that list must be kept in step even though it is currently dormant.

* It needs **no domain**. Like `celery_worker` and `celery_beat` it has no
  `ports`/`expose`, so Coolify won't generate a public router for it.
* The four `PRINT_*` env vars are optional and defaulted; nothing has to be set
  for a LAN printer beyond the per-printer access code, which is entered in the
  app and stored encrypted, not as an env var.
* Its healthcheck is a **heartbeat file**, not `pgrep`. The runtime image is
  `python:3.12-slim`, which ships no `procps` — a `pgrep` check exits 127 and
  leaves the container unhealthy forever. `ListenerSupervisor.touch_heartbeat`
  stamps the file once per pass (including while waiting out a migration, which
  is a live state), and the healthcheck asserts its mtime is under 120s. It is
  the better probe regardless: a wedged loop stops stamping, where the process
  still exists. `celery_beat` carried the same `pgrep` defect and was very
  likely permanently unhealthy in production; it is now fixed separately, by
  reading `/proc/1/cmdline` rather than by a heartbeat, because beat has no
  tick to stamp without app code. Do not translate that one into a scan over
  all of `/proc`: the healthcheck's own argv contains the string it greps for,
  so a scan matches itself and fails open.
* `deploy.replicas: 1` in compose is declarative — plain `docker compose up`
  ignores it outside Swarm. `PrinterLock` is what actually holds the line.
* The container reaches the printer over the host's LAN through ordinary
  bridge-network NAT. Nothing here relies on mDNS or broadcast, which is why
  `PrinterProfile.host` is an IP rather than a hostname.

**The listener races migrations on every deploy, by design of the deploy.** A
Compose resource starts all services together, and `django` runs `migrate` as
part of its own command — so `printer_listener` will regularly come up against
a database that is mid-migration, or briefly gone while Postgres restarts.
`ListenerSupervisor.run_forever` therefore treats both as waits rather than
crashes and calls `close_old_connections()` each pass. Letting either kill the
process would drop the MQTT connection, and if that happened mid-print it would
miss the FINISH transition — the job would close hours later via
`reconcile_stale_jobs` as `unknown`, with the budget debited as a partial
failure rather than a completed print.

## Known gaps
- Per-AMS-slot filament attribution is impossible after the fact: `ams_mapping`
  arrives once at print start and is absent from the snapshot, so a listener that
  wasn't live when the print began can never recover it. What *is* recoverable
  is which spools are loaded right now — that is `filament.py`, and it is why
  the request form's picker is a convenience rather than a record of what a
  print was made from.
- The filament picker reflects the bays at *request* time, and a plate may be
  sliced days later against different spools. `PrintRequest.color` therefore
  stays free text and stores the human-readable name, never a slot: "A2" means
  something else next week.
- Control commands (pause/stop) are not implemented. Firmware 01.08.02+ rejects
  unsigned third-party writes unless the printer is in LAN-Only + Developer mode;
  we only ever publish `pushall`, which is a read.
- The cloud transport's access token expires roughly every three months and
  Bambu's refresh endpoint returns 401 in practice, so a parent re-pastes it. The
  listener surfaces the auth failure on the printer card and stops retrying —
  reconnect loops earn multi-day account bans that lock the household out of
  their own Studio and Handy apps.
