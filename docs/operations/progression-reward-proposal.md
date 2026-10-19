# Expedition and Coin-pouch design experiment

The owner selected 100 automatic Coins per child per day as the starting
experiment. The existing Progression Lab models a hypothetical income
envelope: it omits excess expedition Coins, expedition cosmetic salvage and
opened pouch Coins. Synthetic pouches are consumed in full. This measures an
income hypothesis; it does not simulate a policy suitable for live claims.

## Concrete next candidate

The following fixed table is implemented as the opt-in Lab commitment prototype.
It is not implemented in the live economy. Choose `commitment100` in the saved
experiment notebook or enable `reward_commitment.enabled` in an anonymous run.
The installed control and the earlier payout envelope remain separate modes.

| Expedition | Duration | Proposed direct Coins | Item slots |
| --- | --- | --- | --- |
| Short | 2 hours | 10 | 1 |
| Standard | 4 hours | 25 | 2 |
| Long | 8 hours | 50 | 3 |

Split a child's 100-Coin daily allowance into 75 Coins for expedition
commitments and 25 Coins for random activity pouches. The separate activity
allocation keeps additional mounts from consuming all room for activity
pouches. All of a child's mounts share the expedition allocation.

Before launching a new expedition, establish and reserve its direct Coins,
the full value of any pouch slots and the maximum possible positive cosmetic
salvage. A later trip could offer fewer direct Coins or none; disclose that
before launch and measure how often it happens. Reserve a random activity
pouch's full face value before granting it. Filter candidates that cannot fit
before selection, using the existing tier-weight rules among eligible entries;
never reroll established loot or grant a partial pouch. Empty item slots and
changed item probabilities need explicit measurement.

Preserve existing pouch values of 5, 10, 15, 50, 100, 250 and 500 Coins. A pouch
that does not fit an allocation is unavailable for that new random grant;
already owned pouches still redeem in full. Authored challenge rewards are
established promises, including named large pouches. Keep those outside this
proposed random-grant allocation and report them separately. Reducing those
rewards requires versioned challenge offers established before acceptance.

The allowance resets daily and unused capacity does not bank. It controls new
commitments, not daily wallet credits or every source of Coin earnings. A late
claim or opening may pay more than 100 Coins because the full reward was
established earlier. Track actual Coin payments, unopened pouch value, pending
expedition values and contingent salvage reservations separately. Do not count
a reservation again when it becomes a wallet credit.

## Feedback criteria

Saved comparison criteria select at most six distinct metrics from the server's
fixed list: median Coins earned, median closing Coin balance, median estimated
fulfillment cost in cents, first-priority-offer purchase day and completion
rate, and day reaching 80% of modeled finite content and its completion rate.
Each criterion requires an explicit minimum or maximum; both are inclusive.
There are no free-form report paths or expressions.

Only server-generated paired reports are evidence. Keep the routine, seeds,
horizon, offers, purchasing policy, rules and catalog fixed while comparing an
installed control with the selected envelope or commitment prototype. A report imported
from a file is useful for exploration, but does not establish trusted saved
comparison evidence. A passing comparison can support a decision to continue
design work; it cannot authorize publication or live reward changes.

Day percentiles describe only journeys reaching the milestone within the
horizon. Always display completing journeys and the full trial denominator.
Pair a purchase-day criterion with an explicit required completion rate to
avoid treating two quick purchasers out of ten as success for a typical child.
No completions means insufficient date evidence, not a date equal to the
horizon. A missing metric, disabled purchasing or empty finite-content catalog
cannot pass a check. A comparison with no criteria is unconfigured. Failure
on an available metric remains failure even when another metric is missing.

Use explicit numeric pacing and cost goals chosen for the intended routines;
the notebook does not invent balanced prices or acceptable family costs.
Fulfillment costs are estimates for the entered offers, independent of Coins
and dollars owed to the child. With no eligible real users, observed outcomes
remain unavailable rather than becoming zero costs or successful retention.

## Work required before live implementation

1. Review the commitment simulation against installed rules and the earlier
   payout envelope across 90-day and 365-day routines. Configure explicit pacing
   and cost criteria and record a dated decision against fresh paired evidence.
2. Specify versioned definitions and reservation records that preserve owned
   pouches, frozen expeditions and authored challenge promises. Check retries,
   concurrent launches, delayed claims and outstanding liability accounting.
3. Specify Lucky Coin timing. Live direct expedition Coins can double at claim;
   the current Lab excludes consumable effects and cannot establish a live
   maximum payout. Decide when boosted value is established and reserved.
4. Audit content reachability. Filtering expensive pouches or cosmetics can
   remove acquisition paths. Unavailable content is not longer playable runway.
   Compare first-reward pacing, empty returns, collection completion and
   many-mount advantages alongside purchase timing and balances.

New reward definitions belong in the revisioned content workbench. Expedition
allocation, reservation and boost rules require a reviewed code change.
Independent review, hosted tests and explicit live rollout approval remain
separate from a notebook decision to proceed with design.

## Compare expedition supply independently

Keep the 100-Coin commitment prototype fixed and compare unlimited expeditions,
1/2/3 launches per child per day, and 3/6/9 item promises per child per day.
These allowances are shared across all mounts. The Lab also supports a custom
combined launch/item limit; each comparison must state both values explicitly.
Use matching routine, horizon, seeds, purchasing assumptions and catalog.

Evaluate launched trips, promised/claimed/pending item units, direct Coins,
pouch/salvage commitments, completely empty trip share, first-grown reached rate
and date, 80% finite-content reached rate/date, all-grown and collector chapter
completion, discovery gaps and unavailable targets. Companion selection is the
model's oldest-first policy. Day percentiles without their completion rates
cannot establish a typical timeline. Fewer obtainable targets do not provide
more runway.

An item allowance alone leaves subsequent Coin-only or empty launches enabled.
In a controlled already-grown 15-mount fixture under this Coin prototype, a
3-item limit permits 15 launches but only the first trip receives items, and
13 trips promise neither direct Coins nor items. This fixture demonstrates a
mechanism; it is not a forecast of how often new users reach that situation.
The seeded routine study and saved experiment evidence measure the practical
tradeoff before choosing a live policy. Live reservation storage, concurrent
launches and reward eligibility remain a separate implementation decision.
