# Reading Voyager milestone implementation

This implementation prepares the selected untimed Companion and 84-day,
milestone-gated Voyager for review. It adds native support and an exact private
draft preparation command; deployment does not activate the policy or change
bundled Reading Voyager/Lorebook content. Activation remains a separately
reviewed Workbench publication after deployment of this implementation.

## Selected candidate

Reading Companion is a one-time onboarding milestone: three daily Reading
Adventures, at the child's own pace, with no deadline. Its existing 0 authored
Coins, 20 Reading Comprehension XP, Chick Egg, Base Potion and two Birdseed
remain the reward promise. The private draft prepares this change together
with Voyager; neither definition changes when the implementation is deployed.

Reading Voyager requires the same child's completed global Reading Companion
and unlocked Language Arts::Reading Comprehension at level 1. Its next newly
earned daily Reading Adventure opens an 84-day window and counts as the first
of 20 Adventures. The predecessor-finishing Adventure cannot count again.
Rewards remain 0 authored Coins, 50 XP to the existing skill at weight 1, and
one existing Bookworm title. The title retains its uncommon rarity, 15-Coin
value and saved metadata. There is no tenure or calendar requirement.

The longer window gives twice-weekly readers time to miss visits without
changing the 20-Adventure target or delaying completion for regular readers.
It adds time to use the existing challenge, not authored content. Modelled
outcomes are forecasts from specified routines, not evidence of retention.

## Native behavior

`QuestDefinition` stores protected prerequisite-challenge and skill references
plus the required skill level. Defaults leave existing definitions ungated.
Validation rejects private, ambiguous, cyclic and unsupported references.
An explicit null `duration_days` means untimed and is restricted to one-time
global collection challenges whose only filter is `reading_logged`. New
automatic goals and occurrences retain null `ends_at`; they never acquire a
synthetic distant deadline or repeat. Catalog and goal cards show **No deadline**.
Parent-authored measurable goals retain their timed creation contract.
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
The saved end is exclusive, exactly 84 elapsed days after the accepted source
timestamp; its displayed calendar uses the saved household timezone.

Existing goals retain their original dates, prose, rewards and history,
including unopened 45-day goals and accepted 56-day milestone promises. Paid
or expired one-time automatic goals cannot rearm; a prior accepted legacy
Voyager window also blocks a new milestone-gated Voyager offer. Active legacy
scalar-edit protection still blocks
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
The old Reading Companion's one-time 14-day window opens at the child's first
automatic-goal evaluation: any processed activity (a habit tap, chore or
homework approval, clock-out, journal entry and others), the Today dashboard's
challenge card, or the Challenges page. A child who misses its three readings
in that window may explicitly retry it; reading or opening the page cannot
start that retry. The selected untimed definition removes that deadline: a
child can finish three qualifying Adventures after a late start or a long gap.
An untimed promise never expires, so it is never offered a retry. A child
whose earlier timed Companion window already expired keeps that saved promise:
an explicit retry opens another window with the same 14-day span, not the
untimed definition.
Previously accepted timed Companion promises retain their saved deadline; this
schema migration does not reopen, extend or pay those saved rows. The existing
automatic-tracking cutover can create a child's first catalog Companion goal
after an expired or failed legacy Companion if no automatic goal exists; that
new goal follows the current definition while the legacy row stays unchanged.
New legacy manual starts of untimed definitions are refused; automatic
tracking owns their one promise. Workbench editing, preview, publication,
YAML override retention, MCP catalog exports and Lab snapshots
carry the same exact IDs. Catalog and rules fingerprints invalidate stale
comparisons when those rules change.

## Prepare for review

An operator can explicitly run the command against the intended application:

```bash
python manage.py prepare_reading_voyager --actor-id <active-staff-parent-id>
```

This creates one private draft and normal preview for that exact actor,
containing both the untimed Companion and gated 84-day Voyager edits. It
returns the revision, preview ID, content digest and resolved global IDs. It
refuses baseline/reward drift (including Companion item types, typed Chick/Base
bindings, compatible hatching pair, Birdseed nourishment, quantities and skill
weights), ambiguous identities, foreign ownership or active legacy conflicts
and rolls back draft creation on failure. It never
simulates or publishes. It is not a deployment/startup command.

Review the returned diff, run normal Workbench comparisons, then obtain
explicit approval for that exact publication. Its normal stale-preview,
simulation, ownership and catalog-lock gates remain mandatory. Refresh the
bounded accepted-goal/legacy preflight before activation. This is a prelaunch
change; any synthetic or saved attempts still retain their recorded promises.
Coordinate active bundled YAML and Lorebook copy when publishing, respecting saved
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
snapshots, historical 56-day milestone snapshots, selected 84-day milestone
snapshots, and other or unknown rules. Both milestone groups require the same
strict saved Companion/Reading Comprehension gates and opening activity ID.
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
qualifying live child can still receive that challenge under that historical
policy. The selected 84-day window makes those routines eligible in the model;
that change in the finite-target denominator is not newly authored content.
Missing a month can still exhaust an 84-day window. More forgivable timing
does not change daily reading awards or Voyager’s authored reward, though
restoring a completion can pay its normal one-time rewards and accomplishment
draw. No Coin denomination, expedition budget or other challenge policy is
changed by this implementation.
