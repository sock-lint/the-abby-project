# apps/rewards/

Non-monetary Coins economy + parent-approved reward shop + money→coins exchange. Parallel to `apps/payments/` (money ledger).

## Price planning

Parent shop forms and anonymous Lab offers share an editable planning guide:
50 Coins per active day initially, with Small (3 days / 150 Coins), Medium
(10 days / 500 Coins), and Big (30 days / 1,500 Coins) suggestions. Actual
earnings vary. Parents can change the estimate, enter a custom day target or
set any exact price. Suggestions copy a price only after an explicit click;
changing the guide never recalculates an existing or entered price. Only
`cost_coins` is saved for real offers; Lab uses its explicit `coin_price`.

Newly created missing bundled Streak Freeze offers cost 150 Coins. Startup
seeding preserves every existing family offer, including earlier 60-Coin
prices and parent edits. It cannot infer ownership from a name or price.
Accepted redemption prices and existing balances stay intact. New anonymous
Lab offers use 150 Coins; saved scenarios retain their entered prices and the
backend's older omitted-price normalization stays compatible.

## Available offers and earlier promises (October 2026)

With Egg Discovery enabled, new digital-item/combined egg offers are unavailable
through the shared `reward_is_available` policy and active-offer validation.
Child and parent My space shops, wishlists, suggestions and direct redemption
requests cannot spend Coins or reserve stock for them. Family management keeps
the existing offer for retirement. Earlier frozen paid egg promises still
approve/deliver exactly once after the switch or an offer edit; no inventory,
ledger or reserved stock is rewritten. Real-world-only rewards remain available.

The owner-authorized prelaunch retirement is an exact, one-time exception to
ordinary promise preservation. Before deleting matching obsolete redemptions,
it refunds the net actually recorded Coin hold for pending/approved undelivered
digital-only requests and restores any reserved finite stock. A frozen price
without a recorded debit cannot create a refund. Existing ledger entries remain; appended
refunds can increase the balance. Fulfilled/delivered receipts receive no refund.
Pure digital obsolete offers can be removed; an edited offer needed by an older
supported frozen promise remains deactivated. Real-world and combined offer rows
remain with the obsolete optional item FK cleared. Combined offers are
deactivated and converted to real-world fulfillment. Their frozen combined
receipts retain status, cost, audit and actual debits as real-world promises;
they receive no refund and keep the physical delivery flow. Accounts and
unrelated promises are not reset. See
[unused first-party content retirement](../../docs/operations/companion-lifecycle.md#unused-first-party-content-retirement).

Default startup records success transactionally and skips the transition on
later loads. Identity/protection/resource-validation conflicts roll back all
retirement changes, warn and continue bundled loading without a success marker.
Dry runs and later bundled-load failures roll back both refunds and cleanup;
explicit operator cleanup remains strict. These exceptions do not alter the
ordinary availability and fulfillment rules below.

`availability.py::reward_is_available` allows real-world rewards and requires
an available `item_definition` for digital-item or combined fulfillment.
It delegates item eligibility to the shared supported-art catalog in
`apps/rpg/catalog_support.py`. Child shop lists and similar-reward suggestions
exclude unavailable offers; parent lists retain the rows with read-only
`catalog_available` so they can retire them. Publishing an active unsupported
digital offer is rejected; deactivating an earlier offer is allowed.

`request_redemption` checks eligibility before holding Coins or decrementing
stock. A direct request cannot bypass an omitted offer. Pending redemptions
created earlier still fulfill their saved item exactly once through the
existing approval path, even if new acquisition is now unavailable. Each new
redemption freezes `fulfillment_kind_snapshot` and the exact protected
`item_definition_snapshot` alongside its price. Changing or retiring an offer
cannot replace, remove or add digital delivery to that saved promise. The
protected item cannot be deleted while a redemption references it. An older
digital promise whose item was already missing remains pending on approval
(409), allowing a parent to deny it and refund the held Coins.

Migration `0012` freezes each historical row's last recoverable offer fields,
including fulfilled and denied history, without awarding inventory or changing
ledgers, status, price or decision notes. Original fulfillment edits and finite
stock mode were not historically recorded, so the migration cannot reconstruct
earlier values; it preserves the offer the old decision code would have used.
Denial still refunds the frozen cost and restores reserved stock. Do not rewrite old promises,
delete saved inventory or substitute compensating Coins because art support
changed. `tests/test_digital_fulfillment.py` and
`apps/rpg/tests/test_catalog_consumers.py` cover these boundaries.

## Models
- `CoinLedger` — append-only ledger of Coin transactions. 13 reasons: `hourly`, `project_bonus`, `bounty_bonus`, `milestone_bonus`, `badge_bonus`, `redemption`, `refund`, `adjustment`, `chore_reward`, `exchange`, `daily_challenge`, `expedition`, `reading`. Positive = earned, negative = spent/refunded. Reading's daily Adventure pays 5 base Coins with its own `reading` reason, which honors Lucky Coin; its durable source receipt prevents repeat payments.
  Optional internal `source` attribution records new `expedition`,
  `expedition_salvage` and `coin_pouch` awards at their existing transaction
  boundaries. Blank means historical, unknown or another source; do not infer
  it from descriptions or backfill old payouts. `CoinService.award_coins`
  validates positive amounts and matching reasons for typed sources without
  changing Lucky Coin eligibility, prices, promises or payout amounts. The
  existing ledger REST/MCP response shapes are unchanged. Staff-parent Lab
  observations aggregate only the caller's recent active child cohort and
  expose incomplete attribution rather than reconstructing missing history.
- `Reward` — family-scoped shop items. Rarity tiers (common→legendary), optional stock, `requires_parent_approval`, `order`. **Digital fulfillment**: `fulfillment_kind` (`real_world` / `digital_item` / `both`) + `item_definition` FK to `rpg.ItemDefinition` — approval auto-credits the item to `UserInventory` via `_maybe_credit_digital_item`. Per-family unique constraint on `(family, name)`.
- `RewardRedemption` — submit-then-approve workflow. Digital-only approval becomes `fulfilled`; real-world or combined approval becomes `approved` (awaiting handover), then an explicit parent delivery becomes `fulfilled`. Pending requests may become `denied` and refund; approved promises cannot be refunded through rejection. Inherits `ApprovalWorkflowModel`; `delivered_at`/`delivered_by` record handover separately from the preserved approval audit. Existing fulfilled history is not reopened or assigned an invented delivery date. Price, fulfillment kind, exact digital item and whether finite stock was reserved are frozen at request time. Nested `reward` fields in redemption responses project the saved price/kind/item; shop offer responses retain today's editable values. Other offer metadata remains current.

The `reward_redeemed` badge criterion counts approved and fulfilled requests,
so a child's earned reward remains eligible before physical handover. Delivery
does not count the same redemption twice or repeat its badge payout.
- `RewardWishlist` — `(user, reward)` bookmark. Cleared on restock notification or redemption. Unique constraint per user+reward.
- `ExchangeRequest` — money→coins exchange pending parent approval. Statuses: `pending → approved` or `pending → denied`. Snapshots `exchange_rate` at request time. Money is NOT held at request time — balance re-verified at approval.

## Services

In parent My space (`X-Abby-Space: personal`), shop lists use the same available
active offers as a child, wallet/history requests are self-scoped, and purchases
spend the parent's own Coins. Existing approval, stock reservation and physical
delivery rules remain in force, with no new money payout. Family retains shop
authoring, unavailable-offer visibility and household approval management.

- `CoinService` (extends `BaseLedgerService`) — `award_coins`, `spend_coins`, `get_balance`, `get_breakdown`. Awards apply **Lucky Coin boost** via `coin_boost_multiplier(user)` from `apps/rpg/services` when the reason is on the `_BOOSTABLE_COIN_REASONS` whitelist (excludes `adjustment`, `refund`, `redemption`, `exchange`).
  Spending locks the user's wallet row inside a transaction before checking
  the balance. Optional 3D print exchanges use the same spending path with a
  `redemption` debit and a `refund` credit for cancellation before any print.
  The print request holds its fixed quote and ledger links; no real money moves.
- `RewardService` — `request_redemption` locks/re-reads the authoritative offer before eligibility, price and stock checks, then holds coins and reserves one stock atomically. Stale instances and concurrent buyers cannot sell the final item twice; the loser receives the existing **409 Conflict** with `{error, code: "out_of_stock", similar: [...]}`. `approve` stamps and credits the saved digital item once, including combined offers; a real-world component awaits delivery even when pre-approval is disabled. `deliver` requires a parent in the child's family and records only the handover receipt, without another Coin debit/refund or inventory grant. `POST /api/redemptions/{id}/deliver/` accepts `{}` and returns the full redemption; fulfilled retries return the original result, while pending/denied/canceled or malformed digital-only approved requests return 409. `GET /api/redemptions/?status=approved` is the separate delivery queue; pending approval filters remain unchanged. `reject` refunds the saved price and restores stock only when the request reserved a finite unit and the current offer still uses finite stock. An unlimited request cannot invent a unit after a later stock limit; returning a finite offer to unlimited retains unlimited stock.
- `ExchangeService` — `request_exchange` (validate balance, snapshot rate, notify parents), `approve` (atomic debit `PaymentLedger` + credit `CoinLedger` + chronicle first-ever hook), `reject` (no ledger side-effects — money was never held).

MCP handover permits an inactive child still in the parent's current family,
matching REST's saved-promise workflow. The actor must remain an active parent;
both scalar resolution and the locked household boundary enforce membership.
Delivery and replay keep the original Coin and digital-inventory receipts.

Digital item fulfillment uses the shared locked inventory grant, so a delivered
collection piece immediately evaluates collection badges within the redemption
transaction. Badge bonuses and their completion loot roll back with a failed
fulfillment; an approved/fulfilled retry cannot grant the item or badge again.

## Exceptions
- `InsufficientCoinsError`, `InsufficientFundsError`, `RewardUnavailableError`.

## Gotchas
- **Wishlist restock fan-out**: when a parent edits a reward and stock crosses `0 → ≥1`, `RewardService` fans out `REWARD_RESTOCKED` notifications to every wishlist user and clears their wishlist rows in the same transaction. Each notification also sends an email (2026-06) when email is configured and the user has an address — restocks are time-sensitive and the cleared wishlist row means there's no second chance to reach an out-of-app kid. Production email defaults to the dummy backend without an SMTP host; in-app notifications and wishlist cleanup still run. Configured email failures log via `logger.exception` without breaking the in-app fanout (same posture as the weekly-summary emails in `apps/timecards/tasks.py`); pinned by `RestockEmailTests` in [`tests/test_views.py`](tests/test_views.py).
- **Low-stock signal**: `request_redemption` fires `LOW_REWARD_STOCK` notification to parents the first time stock enters 0 or 1.
- **Offer writes**: REST and MCP updates re-read under the same offer lock as reservations. Metadata-only edits retain the current stock; an explicit stock value remains an intentional restock. Wallet/decision services lock the child before the offer (or child, redemption, offer); metadata edits take only the offer lock, and notification FKs remain compatible with the child's `NO KEY UPDATE` lock.
- **Coin boost whitelist**: when adding a new earn-kind `CoinLedger.Reason`, decide whether it belongs in `_BOOSTABLE_COIN_REASONS` (`apps/rpg/services.py`) and add a regression test in `apps/rpg/tests/test_boost_multipliers.py`.
- **`Reward.save()` defense-in-depth**: auto-attaches to default family when `family_id` is None (same pattern as `User`, `ProjectTemplate`, `Chore`).

## Key entry points
- `services.py` — `CoinService`, `RewardService`, `ExchangeService`.
- `models.py` — `CoinLedger.Reason` choices, `Reward.FulfillmentKind`, `RewardRedemption.Status`.
