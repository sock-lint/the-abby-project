# Coin earning and shop pacing

New expeditions use 3 / 7 / 15 base Coins for the existing 2 / 4 / 8 hour
durations. Each child can start two trips per family-local day across all
species, with the existing one-trip-per-species limit inside that allowance.
Saved launch history counts even after claiming or expiry. The existing small
random variation, item slots and Lucky Coin claim-time multiplier still apply.
This is an 80% reduction in base payout, not an all-source daily Coin cap.

New random Coin pouches pay one fifth of their previous denominations:

| Original pouch | New random pouch |
| --- | --- |
| 5 | 1 |
| 10 | 2 |
| 15 | 3 |
| 50 | 10 |
| 100 | 20 |
| 250 | 50 |
| 500 | 100 |

The smaller pouches have separate item identities. A random selection keeps
its original probability and rarity, then grants the corresponding smaller
pouch. This applies to activity and accomplishment drops and new expedition loot.
Owned Mystery Box and Lucky Dip effects retain their original outcome values.
New pouch names and inventory explanations show their smaller value. Authored challenge and shop item rewards retain their exact item IDs.
Custom pouches outside the bundled mapping retain their authored values.

No balance is rescaled. Original pouch definitions and owned stacks retain
their full values. Expeditions save direct Coins and selected items at launch;
claiming a trip accepted earlier pays its saved loot. Quest and challenge
fulfillment keep accepted item promises. Shop redemptions keep their frozen
price, item and fulfillment kind, including refunds at the accepted price.
New random-pouch identities are additive; loading content again must not
convert old inventory, reroll pending trips or rewrite accepted rewards.
The additive upgrade checks reserved replacement identities before inserting
anything. An incompatible pre-existing identity stops the upgrade rather than
adopting or repricing an owned custom item.

## Shop saving-time guide

The parent reward form offers an optional planning guide. Its starting
assumption is 50 Coins per active day, with small / medium / big targets of
3 / 10 / 30 active days: 150 / 500 / 1,500 Coins. Parents can change the
earning estimate, choose a custom number of active days, apply a suggestion
and edit the exact Coin price. Nothing changes the stored price until the
parent saves the offer. An active day means a day with normal meaningful
activity, rather than elapsed calendar time.

These are planning assumptions, not observed household averages, guaranteed
payouts or daily allowances. Different routines, existing savings, collection
size, authored rewards and boosts affect the actual saving time. Use the
family's Coin history and the anonymous Progression Lab to revisit the
assumptions after collecting evidence.

Newly seeded Streak Freeze offers start at 150 Coins. Existing family offers
keep their current prices: bundled startup seeding does not own or overwrite
parent-authored shop rows. Parents can explicitly reprice those offers in the
same form. Saved Lab experiments and their explicit offer prices remain intact.

The parent reward form warns when an unlimited digital-item or combined offer
charges fewer Coins than its selected Coin pouch pays. The message shows the
price, payout and net gain per purchase; parents can still save their chosen
offer. Finite stock, a price at or above the payout, other item types and an
unknown pouch payout do not show this warning. The guide and warning never
reprice an offer automatically.

## Progression Lab

The installed-rule control models the smaller new expedition and random-pouch
awards while retaining original pouches for authored rewards and existing consumables.
It also mirrors the installed shared launch limit, future cosmetic salvage
and distinct-active-day challenge accounting. Saved experiments retain their
recorded policy and reports; changed rule fingerprints make older evidence
explicitly historical. Policy and catalog
fingerprints invalidate stale comparisons without rewriting historical reports.
The separate [100-Coin commitment prototype](progression-reward-proposal.md)
remains hypothetical. Its 75 / 25 allocations and 10 / 25 / 50 expedition table
are separate assumptions and do not describe the installed payout reduction.

Validation uses synthetic inventories, accepted expeditions, challenges and
shop requests. No production account, balance or offer is changed by tests.

## New savings milestones

New goals freeze their reward rate and a starting floor above both current
money and the highest previously completed target. The durable per-child
admission high-water mark survives goal deletion, spending, payouts and
exchanges. Separate ordered, merged ranges in integer cents record money
already recognized or excluded at cutover. Completion subtracts that coverage
from the goal's frozen starting-floor-to-target range and pays its frozen rate
on the total uncovered dollars once. Overlapping new goals cannot reward the
same saved dollars twice. A goal already covered
by existing money can be visibly complete without Coins, drops, challenge
credit or savings-badge progress.

The admission maximum does not imply every lower dollar has been rewarded.
For example, an older $100 goal started at $0 retains its unpaid $0–60 range
when a later goal started at $60 rewards only $60–80. The older goal later
recognizes that lower gap and $80–100; the paid $60–80 range is excluded.
Already funded completions add no coverage. They may raise the admission
maximum, preventing fresh identities from acquiring old gaps after spending.

Changing a new goal's target starts its reward eligibility above the greatest
of its previous starting floor, current money and the admission maximum. Lowering old
targets after a deposit cannot split that existing money into extra milestone
credits. Sending the same target or changing only its title or icon preserves
the frozen baseline and any legitimate reward retry. Legacy goals retain their
accepted fixed rewards when edited.

When one write reaches several new targets, their positive savings increments
retain their individual frozen Coin rates. Only the highest target contributing
new savings counts as a qualifying milestone for drops, challenges and savings
badges; the other goals still complete visibly. Legacy completions retain each
accepted reward event.

The additive migration freezes each existing goal's accepted target and old
Coin promise, and marks existing goals as eligible under their established policy. It seeds
high-water history without ledger writes, notifications or completion rewards.
Existing accepted goals retain their fixed payouts. REST, pulse and MCP reads
never settle goals; explicit goal changes and money ledger writes own
completion. Client cards and completion toasts do not invent target-times-rate
payouts. Actual Coin awards remain in the server's ledger and notifications.
An accepted legacy goal can be renamed or given a higher target while keeping
its original Coin promise. Its target cannot be lowered below the frozen
accepted amount; REST and MCP return a field validation error. A lower target
requires a new prospective goal, so a large accepted payout cannot be claimed
by changing its original requirement to an already funded smaller amount.
Legacy completion reserves coverage only through its frozen accepted target;
a raised target updates admission without erasing another old goal's unpaid gap.

## Future challenge windows

Explicit version-2 bundled offers use the following rewards. Their existing
accepted windows keep their saved targets, progress, items and payout receipts.
Only newly accepted or recurring windows use the new rules; parent-authored
and unversioned custom offers retain their authored policies.

| Challenge | Future requirement | Coins | Extra items |
| --- | --- | ---: | --- |
| First Week of Freshman Year | 5 habit activity days in 7 days | 20 | Existing authored collectible |
| Seven Nights of Stories | 5 earned Reading Adventure days in 7 days | 20 | Existing authored items |
| Weekly Reset | 5 habit activity days in 7 days | 10 | No Coin pouch |
| Comeback Kid | 3 habit activity days in 7 days | 10 | 1 Streak Freeze |
| Comeback Kid II | 5 habit/chore activity days in 7 days | 15 | 1 Streak Freeze |
| Pantry Patroller | 5 approved chore activity days in 7 days | 10 | No Coin pouch |
| Daily Rituals | 3 positive habit actions in its existing one-day window | 2 | No Coin pouch |

A distinct activity day is computed from accepted source timestamps in the
window's saved family timezone. Multiple actions on that day contribute once;
voided activities stop contributing. A deadline alone is not an activity-day
requirement for other challenges. Ambiguous duplicate system definitions retain
current accepted windows but cannot create more future cycles. Reviewed
canonical identity publication remains a separate existing workflow.

## Other prospective awards

New ordinary random cosmetic duplicates pay at most 10 Coins each, without
changing catalog ownership or rarity odds. New expeditions freeze that amount
in each cosmetic slot at launch; claims never recalculate it. Old trips without
the new snapshot and owned consumables keep their existing effects and values.
Guaranteed authored rewards and older inventory are not rewritten.

Future annual birthday gifts use the fixed `BIRTHDAY_COIN_GIFT=200`, independent
of age. Previously saved birthday receipts and Coin balances remain unchanged.
Money exchange remains `COINS_PER_DOLLAR=10`, including each pending request's
frozen quote. Accepted shop redemptions retain their original cost, fulfillment
and refunds even when a parent updates the offer price for new requests.

The owner-directed family shop price update is an explicit MCP operation,
verified separately from deployment. It does not introduce a migration that
reprices other families' parent-managed offers.

## Catalog rollout holds

Bundled loading keeps its existing provenance and ambiguity checks. An
unreconciled duplicate, active legacy campaign, pack-owned row or database
override can hold a source update. Such rows are not silently chosen or
replaced with version-2 rules. Already saved occurrences, including future
windows, remain accepted promises; the new guard stops creating additional
ambiguous cycles. For duplicate identities, the separately reviewed canonical
reconciliation workflow must publish its exact pair before a bundled reload
or reviewed version-2 publication can update the canonical offer. Installing
that workflow alone does not change saved catalog data.
