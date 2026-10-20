# Reading Voyager milestone implementation

This implementation adds inactive native support and an exact private draft
preparation command. It does not publish the selected policy or change bundled
Reading Voyager/Lorebook content. Activation remains a separately reviewed
Workbench publication after deployment of this implementation.

## Selected candidate

Reading Voyager requires the same child's completed global Reading Companion
and unlocked Language Arts::Reading Comprehension at level 1. Its next newly
earned daily Reading Adventure opens a 56-day window and counts as the first
of 20 Adventures. The predecessor-finishing Adventure cannot count again.
Rewards remain 0 authored Coins, 50 XP to the existing skill at weight 1, and
one existing Bookworm title. The title retains its uncommon rarity, 15-Coin
value and saved metadata. There is no tenure or calendar requirement.

## Native behavior

`QuestDefinition` stores protected prerequisite-challenge and skill references
plus the required skill level. Defaults leave existing definitions ungated.
Validation rejects private, ambiguous, cyclic and unsupported references.
This release supports gates only on one-time global collection challenges
whose sole activity is `reading_logged`, without additional filters. Adding
another source requires its own trusted acceptance hook and behavioral tests.

The reading reward service observes eligibility after its real XP award and
before processing the newly earned daily receipt. Under the existing account
lock it captures the goal, occurrence, rule/reward snapshot and first activity
ID. Reading logs still need ten new minutes and reward at most once per
family-local day. Reads, pins, old-source replay, source scans and pending
repairs cannot accept a new milestone window. A retry can finish processing
an already accepted receipt without changing its promise or paying twice.
The saved end is exclusive, exactly 56 elapsed days after the accepted source
timestamp; its displayed calendar uses the saved household timezone.

Existing goals retain their original dates, prose, rewards and history,
including unopened 45-day goals. Paid or expired one-time goals and prior
legacy starts cannot rearm. Active legacy scalar-edit protection still blocks
publication. New solo, co-op and scroll starts cannot open gated reading
challenges manually; after meeting the milestones, the next Reading Adventure
opens them automatically. Rerolls exclude these automatic definitions.
Accepted legacy runs keep their own promise. Item hints preserve accepted
rewards and filter new locked offers.

The child Challenges page displays server-confirmed requirements in **Coming
next**, with no countdown before acceptance. Requirements can be met while
the page awaits the next matching saved activity. An expired unpaid catalog
prerequisite can be explicitly retried while the server says it is eligible.
Its successors remain discoverable; only definitely unavailable paths are
omitted. A retry starts a fresh window and counts new qualifying facts.
Reading Companion's one-time 14-day window opens at the child's first
automatic-goal evaluation: any processed activity (a habit tap, chore or
homework approval, clock-out, journal entry and others), the Today dashboard's
challenge card, or the Challenges page. A child who misses its three readings
in that window may explicitly retry it; reading or opening the page cannot
start that retry. Workbench editing, preview,
publication, YAML override retention, MCP catalog exports and Lab snapshots
carry the same exact IDs. Catalog and rules fingerprints invalidate stale
comparisons when those rules change.

## Prepare for review

An operator can explicitly run the command against the intended application:

```bash
python manage.py prepare_reading_voyager --actor-id <active-staff-parent-id>
```

This creates a private draft and normal preview for that exact actor. It
returns the revision, preview ID, content digest and resolved global IDs. It
refuses baseline/reward drift, ambiguous identities, foreign ownership or
active legacy conflicts and rolls back draft creation on failure. It never
simulates or publishes. It is not a deployment/startup command.

Review the returned diff, run normal Workbench comparisons, then obtain
explicit approval for that exact publication. Its normal stale-preview,
simulation, ownership and catalog-lock gates remain mandatory. Refresh the
bounded accepted-goal/legacy preflight before activation; a statement that
the app has no active users is not evidence of zero saved goals. Coordinate
active bundled YAML and Lorebook copy when publishing, respecting saved
database overrides. Existing goals are not migrated to a longer window.

## Observe after rollout

The staff Lab's **Reading Voyager feedback** panel reads
`GET /api/challenges/voyager-feedback/` independently of anonymous simulation.
It reports a current cohort of active nonstaff children in the observer's own
family registered within 180 inclusive family-local days. All their saved
Voyager windows are considered, including those created more than 30 days ago.
Trusted observer families are excluded. The fixed bounds are 100 children and
10,000 saved records; unavailable totals stay unknown rather than partial.

Current child states distinguish locked, ready, active, completed, expired and
unknown. Readiness uses today's rules, not a historical unlock timestamp.
With native gates, ready means waiting for the next qualifying new Reading
Adventure. Before activation, ungated Voyager retains automatic tracking.

Saved policy groups classify accepted 45-day windows without native milestone
snapshots, the selected 56-day milestone snapshot, and other or unknown rules.
The groups use immutable saved promises, not today's catalog configuration.
Older badge-only eligibility and legacy full policies cannot be reconstructed.
These groups do not establish identical rewards or a causal policy effect.
Canonical catalog identities include their exact retained history aliases.
Each valid attempt in a linked retry chain contributes its own saved window
to the policy groups. Each child contributes once to current states, using
the latest attempt or a valid lifetime completion. Unlinked duplicates,
conflicting goals and malformed chains remain unknown. A closed attempt
without a resolved outcome stays unknown rather than becoming a failure.

Wait for each full saved deadline before including its outcome in a mature
completion rate. An early completion can already appear completed in the child
snapshot while its window remains under observation. The denominator is known
mature completions plus known mature expiries; pending and unresolved evidence
are excluded. This denominator counts attempt windows, not distinct children.
With no resolved mature outcomes, show insufficient evidence
rather than zero-percent success. Later source processing can resolve an
earlier unknown outcome; completion timestamps describe processing, not lateness.

Review current gates and active windows as new families arrive; review the
full-window rates once the accepted cohort has reached its saved deadlines.
Use low counts and unresolved evidence as a reason to inspect coverage before
changing content. The report never materializes goals, expires saved rows,
backfills contributions or awards rewards. It does not publish this policy.

The MCP `get_voyager_feedback` tool returns the same aggregate with empty
`params`, without a child/family selector or a date override. It requires an
active staff parent and an explicitly authorized `mcp:read` grant; catalog-only
connections cannot discover or invoke it. Deploying this tool does not expand
an existing connection's permissions. Use the household-read consent flow if
the owner chooses to make these observations available in a connected chat.

## Forecast limits

Anonymous Lab trials start at zero and cannot establish retention or total
application exhaustion. The Lab excludes offers it calculates a routine
cannot finish; live enrollment does not predict attendance. In particular,
two reading visits per week cannot fit 20 Adventures in 56 days, but a
qualifying live child can still receive that challenge. No Coin denomination,
expedition budget or other challenge policy is changed by this implementation.
