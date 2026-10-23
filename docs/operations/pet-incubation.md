# Timed egg incubation

Pets → Hatchery keeps the existing egg shelf and four-stage family guide.
Family previews follow the child surprise rule in `companion-lifecycle.md`.
Choose an owned egg and compatible potion, review the wait, then choose
**Start incubation**. The accepted start consumes one of each ingredient and
saves the egg's identity and deadline. It creates no pet or reward yet.

There is one unfinished incubation per account. A ready egg still occupies
that place until its owner explicitly chooses **Hatch pet**. The resulting
Baby enters the collection at zero growth; the confirmed receipt offers a link
to care for that exact pet. Existing badge and Chronicle hooks run at that
confirmed hatch, rather than at the start or when the timer reaches zero.
Care, Middle at 50 growth, confirmed Grown evolution at 100, and expeditions
keep their existing rules. Breeding remains retired.

## Time and accepted promises

`PET_INCUBATION_DURATION_SECONDS` defaults to 86400 (24 hours). A start freezes
its own deadline, so later setting changes affect only new starts. The server
owns readiness and the saved timer continues while all clients are closed.
No background task, open browser, check-in, food or currency is needed to make
an accepted egg ready. There is no automatic hatch or expiration.

The Hatchery displays a countdown from the server's remaining time, refreshes
on resume and at the expected deadline, and requires a fresh server-ready
response before enabling hatch. A changed phone clock never grants a pet.
Failed reads retain known status and offer a read-only retry. The initial read
must succeed before another start is offered.

Start validation uses the current supported catalog, compatibility and owned
species/potion rules. Accepted incubations retain their ingredient and family
presentation snapshots and remain hatchable after later catalog retirement.
They do not consume a second pair at claim. There are no cancellation, refund,
extra-place, speed-up or breeding mechanics in this flow.

## API and retry behavior

- `GET /api/pets/incubations/` returns the signed-in account's current
  incubation or null, current duration and server time. It grants nothing.
- `POST /api/pets/incubations/` accepts `egg_item_id`, `potion_item_id` and a
  stable UUID `request_id`. The same UUID and pair replay the accepted start;
  changed ingredients under that UUID or another unfinished incubation return
  HTTP 409. Ingredient validation failures preserve inventory.
- `POST /api/pets/incubations/<id>/hatch/` explicitly claims that account's
  ready egg. Early claims return HTTP 409 and foreign or missing IDs return
  HTTP 404. A successful response carries the confirmed pet and
  `freshly_hatched`; a replay returns the same pet with false, without another
  badge payout, pet or item consumption.
- The authenticated legacy `POST /api/pets/hatch/` returns HTTP 410 without
  consuming inventory. MCP exposes the same read/start/claim lifecycle through
  the shared services; its earlier instant hatch action is retired.

Start and hatch transactions take the existing achievements user gate before
locking inventory or incubation. This serializes competing devices and keeps
ownership, item consumption and existing badge payouts atomic. Database
constraints enforce one unfinished incubation per account and one accepted
start per account/request UUID. API fixtures use synthetic identities and the
actual start, wait, ready, hatch and replay producers.

## Progression Lab boundary

The Lab records the installed incubation policy with metadata and each report.
It reserves one compatible egg/potion pair during active care, advances the
frozen elapsed-time deadline on inactive days too, then claims at the next
active care visit. The daily visit model does not predict real return habits
or phone timing. Pending eggs remain separate from owned companions and
completed milestones. Pet badge payouts run at hatch and growth transitions.

Saved control/candidate comparisons share one immutable policy snapshot even
if the setting changes during calculation. A real later policy change makes
older evidence stale and blocks new decisions without rewriting saved bodies.
The commitment and expedition-quota models preserve this same snapshot in
their finite-content comparators. Reforecast after a policy or model change;
older immediate-hatch calibration remains a historical baseline.
