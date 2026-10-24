# Reading Voyager: milestone unlock and 56-day window

**Status:** Proposal for review, October 19, 2026. The owner selected this
direction and requested the proposal and implementation plan only. This
document does not authorize implementation, publication or deployment.

Reading Voyager should become a later reading goal that a light but consistent
reader can finish after a week away. Unlock it after the same child completes
Reading Companion **and** reaches Reading Comprehension level 1. Then give the
child 56 days to complete 20 daily Reading Adventures.

The [review-only policy record](reading-voyager-proposal.json) contains the
exact proposed values. The [implementation plan](reading-voyager-implementation-plan.md)
describes the server work and evidence required before this can be published.
Neither document is an importable content pack or a saved Workbench draft.

## Proposed rule

| Setting | Current catalog | Proposed |
| --- | --- | --- |
| Definition | Reading Voyager, system collection challenge | Same identity and name |
| Unlock | No authored badge requirement | Reading Companion completed AND Reading Comprehension level 1 or higher, for the same child |
| Completion window | 45 days from opening | 56 days from opening |
| Target | 20 qualifying daily Reading Adventures | Unchanged |
| Qualifying work | `reading_logged`, after ten newly logged reading/listening minutes, at most once per family-local day | Unchanged |
| Authored rewards | 0 Coins, 50 XP to Reading Comprehension, one Bookworm title | Unchanged |
| Recurrence | One-off | Unchanged |
| Tenure / offering dates | None | None |

Level 1 means the named skill's level, currently 100 XP; it is not character
level or the level of any other skill. Both milestones are required. Existing
native eligibility and actual earned-badge conditions continue to apply.
There is no 14-day tenure rule, streak requirement or fixed calendar season.

Proposed challenge description:

> Unlock by completing Reading Companion and reaching Reading Comprehension
> level 1. Complete 20 daily Reading Adventures within 56 days after this
> challenge opens. Each Adventure needs ten newly logged reading or listening
> minutes and counts once each family-local day. Earn the Bookworm title.

The window starts when a new qualifying fact opens an eligible offer. The
deadline is exclusive, following the native challenge convention. Browsing a
locked definition must not start the clock. The implementation must retain
the existing household timezone rules and cover precise timestamp/DST edges;
the Lab's numbered days do not prove those live boundaries.

Only Reading Voyager is proposed for live change here. Reading Companion,
Reading Routine, Iron Chef, Treasure Hunter and both Phoenix Rising definitions
keep their current rules. The larger Lab recipe is evidence context, not
authorization to gate those other challenges.

## Identity and reward checks

The read-only global catalog was checked again on October 19:

- Reading Voyager: captured definition ID **69**, system collection, target 20,
  45 days, `reading_logged`, nonrepeatable, no required badge.
- Reading Companion: captured definition ID **67**, system collection, target 3
  within 14 days. Its existing rewards and rules remain intact.
- Skill: captured ID **92**, `Language Arts::Reading Comprehension`, unlocked by
  default. Voyager's existing XP tag has weight 1.
- Reward: captured item ID **97**, slug `title-bookworm`, quantity 1. Keep its
  existing identity, metadata, rarity and 15-Coin value.

IDs are capture references, not portable identifiers or proof of pack ownership.
Before applying anything, resolve exact current identities, global/system
classification, ownership and expected old values. Refuse missing or ambiguous
matches. Do not adopt a row into a new pack by its display name.

Zero authored Coins does not remove existing duplicate-item or salvage rules.
Those rules remain intact; the measured new-user duration pairs below had no
Coin difference. This proposal does not promise that every possible account
has identical downstream rewards.

## Evidence and its limits

The private native study ran **1,110 synthetic new-user journeys across 114
cases**, each covering 90 elapsed days. It used the captured production global
catalog and local engine commit
`12c1f694516a575210998c7f1b21fe4c7aaccee1` from
[PR #291](https://github.com/sock-lint/the-abby-project/pull/291).
It did not run simulations in production or inspect household records.

For the modeled light routine (three visits per week, ten reading minutes,
one chore and one habit per visit), milestone-mode results were:

| Window | No interruption, 20 trials | Week 4 away, 5 trials | Weeks 4 and 6 away, 5 trials |
| --- | --- | --- | --- |
| 45 days | 0 complete; expires at 19/20 | 0 complete | 0 complete |
| 49 days | 20 complete on day 57 | 0 complete | 0 complete |
| **56 days** | **20 complete on day 57** | **5 complete on day 64** | 0 complete |
| 63 days | 20 complete on day 57 | 5 complete on day 64 | 5 complete on day 71 |

Days count from the first modeled visit, not from unlock. The light milestone
offer opens on day 10 and credits that day's reading. Both reading-only
omissions and separately modeled whole-app absences produced these completion
thresholds. Successful 56-day controls at five visits per week kept their
completion dates when only the deadline changed.

All **840 same-seed duration pairs** preserved Coin balances, Coin sources,
final RNG state and first-pet/first-mount timing. Rescued completions awarded the
existing 50 XP and two existing finite identities: Voyager and Bookworm. This
recovers access to authored content; it creates neither additional content nor
a measured retention improvement. The study supplies no full-app exhaustion
date or annual runway forecast.

The study held a **five-target** milestone recipe fixed, including the other
challenges listed above. It isolates duration changes within that recipe; it
does not establish an isolated Voyager-only rollout result. Before live
review, rerun the narrower policy in the implementation plan. Seeds vary native
reward randomness, not attendance uncertainty; these counts are not estimated
player completion probabilities.

At two reading days per week, 20 daily receipts do not fit this 56-day window.
The Lab excluded Voyager from its routine-capacity subset. Live enrollment has
no prediction of future attendance and would not automatically withhold this
offer. The candidate therefore supports the tested three-or-more-reading-days
routine, not every light-user routine. An 84-day alternative completed the
modeled two-visit routine with more margin, but is not selected here. Two missed
weeks also exceeded the selected 56-day candidate's tested allowance.

The fixed interruption schedules used a private calendar harness; they are not
standard Lab scenario imports. Different-duration catalogs also cannot be
recorded as an ordinary same-catalog Notebook pair. A publication review must
use fresh, correctly bound evidence rather than relabeling these reports.

Evidence locator (private station storage, outside Git):
`~/.local/state/abby-owner-chats/reading-voyager-windows-20261019/` contains
`decision-brief.txt`, `study/summary.csv`, `root-aggregate-audit.json` and
`reading-voyager-window-comparison.zip`.

- Study source-freeze SHA-256:
  `97952170867865f355d28d1ffdc6afb3aab9fe12c65cea93f477df4d8d9b21ed`.
- Evidence archive SHA-256:
  `7aa93958296f06c97cf0fd46b936651604c8b2ba2b54afa9fa1f2cbbe06d32dc`.

Repeated global reads matched the captured rows; they were not one atomic
database snapshot. MCP does not attest the deployed engine's source identity.

## Existing promises and publication boundary

Milestone gates are currently **Lab-only**. `QuestDefinition` and the content
Workbench support an earned-badge requirement, but not this prerequisite-quest
AND named-skill rule. An ordinary Workbench duration/description edit would
implement only part of the proposal. A substitute badge or description alone
would not enforce the selected milestones. Do not publish that partial edit.

Apply the eventual rule to future offers. Grandfather every saved
`ChallengeGoal` and its occurrences, including unpinned, unopened, incomplete,
expired and paid rows. Preserve their dates, descriptions, contributions,
rewards and receipts. Do not extend an accepted 45-day goal, relock it, restart
an expired goal or issue another Bookworm award. A template edit does not
update these saved promises automatically.

An active legacy `Quest` still relies on definition scalars, so existing
publication guards block the duration edit while such a run exists. Counts
are unknown from global catalog reads. Hold publication if that guard fires;
do not bypass it or create a second Voyager definition as a workaround. A new
definition could enroll alongside the old one and create another payout.

The eventual release must update the bundled reading-adventures definition,
its description and the Reading Adventure Lorebook explanation together.
Respect Workbench overrides and pack ownership. Deploying gate support must
not silently activate a gate or duration change before that exact policy is
reviewed and explicitly published.

## Review outcome requested

Review this policy, its grandfathering rule and the implementation plan. This
proposal contains no runtime code, migrations, catalog edits, production drafts,
Notebook decisions or publication action. A separate implementation review,
required hosted checks, independent review and explicit rollout decision remain
necessary. The [plan](reading-voyager-implementation-plan.md) defines how to
establish those proofs and measure the result after sufficient elapsed time.
