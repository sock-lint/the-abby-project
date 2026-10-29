# Egg discoveries

This is an opt-in preview. `EGG_DISCOVERY_ENABLED` defaults to false; disabled
authenticated GETs return an empty envelope and discovery mutations are refused.
Movement writes still retain a zero-credit source-identity tombstone while off,
without changing activity rewards or creating targets, searches or egg progress.
Reading has its own persistent request-credit identities; its adapter checks
those native receipts before admitting discovery credit.
Installing the schema does not turn off existing challenges, random eggs,
shops or expedition rewards. A separate reviewed acquisition transition must
preserve accepted legacy promises and audit the combined economy before enablement.

The API is self-scoped for children and parents' own accounts, including My
space. It rejects `user_id` selectors. API operations recheck current active
membership under Family → account `NO KEY UPDATE` locks; source adapters already
hold their account gate and must never acquire a Family lock afterward. Every
selection, activity credit, search and inventory payout shares that account gate.
PostgreSQL constraints retain one active discovery and one lifetime target pair.

Offers are read-only projections of exact typed, supported egg/potion pairs.
New acceptance uses the existing bounded ingredient catalog SHARE/NOWAIT fence
and freezes requirements, item IDs, display labels and seasonal dates. Species,
potion and reward-item references are protected. Completion takes that fence
again, reloads bindings and refuses changed identities without substituting
rewards. Availability withdrawal does not revoke an accepted promise. Seasons
gate only initial selection using inclusive family-local dates; pause/resume
never resets progress or introduces a completion deadline.

`credit_activity` accepts only new saved source facts. The reading adapter uses
full newly logged minutes, independently of its capped daily Reading Adventure.
Movement credit is independent of its three-session XP/drop cap. Immutable source
UUID tombstones retain initial allocation, including zero-credit, historical and
no-active cases. Corrections, deletion, retries and switching targets cannot move
those minutes into another discovery. There is no historical backfill.
Migration `0002` only preserves owner/UUID, saved date and minutes from surviving
movement sessions with a UUID as zero-credit identities. It creates no target,
progress, search or reward. Requests deleted before deployment have no surviving
identity evidence to preserve; sessions without a UUID cannot recover a request
identity. New movement UUIDs remain reserved even while the preview is disabled.

Ordinary completion needs 240 total minutes and at least 90 minutes in each of
two categories. Rare searches use cumulative totals from reading, movement and
making/practice: each search represents 60 minutes, with at most 30 from one
category. For total `T` and largest category `M`, capacity is
`min(T // 60, (T - M) // 30)`. All three categories may contribute; do not round
each category into separate chunks or greedily consume pairs, because source
order and session splitting must not strand effort. Search results are saved
once; new activity only executes capacity beyond the saved search count.
Searches 1–4 have 20% success; search 5 guarantees the selected egg. The engine
stops after success, and residual activity stays attached to that discovery.

Request UUIDs retain normalized command identities. Matching retries return the
current envelope without repeating a mutation; changed payload/action conflicts.
Practice records require a name and 1–240 minutes, with no project configuration
or authored Coins, XP, quest completion or accomplishment drop. Discovery grants
its frozen egg, compatible potion and two common-food units through the shared
inventory service. Existing inventory badge evaluation retains its own reward
authority; any future balance audit must include those indirect rewards.

Run `python manage.py test apps.egg_discoveries --settings=config.settings_test`
with a disposable database. `tests/test_concurrency.py` requires PostgreSQL and
observes real competing account/catalog locks; SQLite skips those tests.
