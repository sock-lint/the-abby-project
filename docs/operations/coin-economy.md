# Coin earning and shop pacing

New expeditions use 3 / 7 / 15 base Coins for the existing 2 / 4 / 8 hour
durations. The existing small random variation, item slots, species daily
allowance and Lucky Coin claim-time multiplier still apply. This is an 80%
reduction in the base payout. It is not a shared daily income cap: owning more
species still provides more expedition opportunities.

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
pouch. This applies to activity and accomplishment drops, Mystery Boxes and
new expedition loot. Their names and inventory explanations show the new
value. Authored challenge and shop item rewards retain their exact item IDs.
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

## Progression Lab

The installed-rule control models the smaller new expedition and random-pouch
awards while retaining original pouches for authored rewards. Policy and catalog
fingerprints invalidate stale comparisons without rewriting historical reports.
The separate [100-Coin commitment prototype](progression-reward-proposal.md)
remains hypothetical. Its 75 / 25 allocations and 10 / 25 / 50 expedition table
are separate assumptions and do not describe the installed payout reduction.

Validation uses synthetic inventories, accepted expeditions, challenges and
shop requests. No production account, balance or offer is changed by tests.
