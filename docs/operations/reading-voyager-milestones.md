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
the page awaits the next matching saved activity. Workbench editing, preview,
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

## Forecast limits

Anonymous Lab trials start at zero and cannot establish retention or total
application exhaustion. The Lab excludes offers it calculates a routine
cannot finish; live enrollment does not predict attendance. In particular,
two reading visits per week cannot fit 20 Adventures in 56 days, but a
qualifying live child can still receive that challenge. No Coin denomination,
expedition budget or other challenge policy is changed by this implementation.
