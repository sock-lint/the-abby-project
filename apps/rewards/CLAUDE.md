# apps/rewards/

Non-monetary Coins economy + parent-approved reward shop + money→coins exchange. Parallel to `apps/payments/` (money ledger).

## Models
- `CoinLedger` — append-only ledger of Coin transactions. 12 reasons: `hourly`, `project_bonus`, `bounty_bonus`, `milestone_bonus`, `badge_bonus`, `redemption`, `refund`, `adjustment`, `chore_reward`, `exchange`, `daily_challenge`, `expedition`. Positive = earned, negative = spent/refunded.
- `Reward` — family-scoped shop items. Rarity tiers (common→legendary), optional stock, `requires_parent_approval`, `order`. **Digital fulfillment**: `fulfillment_kind` (`real_world` / `digital_item` / `both`) + `item_definition` FK to `rpg.ItemDefinition` — approval auto-credits the item to `UserInventory` via `_maybe_credit_digital_item`. Per-family unique constraint on `(family, name)`.
- `RewardRedemption` — submit-then-approve workflow. Statuses: `pending → fulfilled` (approved) or `pending → denied`. Inherits `ApprovalWorkflowModel`. `coin_cost_snapshot` freezes cost at request time for refund accuracy.
- `RewardWishlist` — `(user, reward)` bookmark. Cleared on restock notification or redemption. Unique constraint per user+reward.
- `ExchangeRequest` — money→coins exchange pending parent approval. Statuses: `pending → approved` or `pending → denied`. Snapshots `exchange_rate` at request time. Money is NOT held at request time — balance re-verified at approval.

## Services
- `CoinService` (extends `BaseLedgerService`) — `award_coins`, `spend_coins`, `get_balance`, `get_breakdown`. Awards apply **Lucky Coin boost** via `coin_boost_multiplier(user)` from `apps/rpg/services` when the reason is on the `_BOOSTABLE_COIN_REASONS` whitelist (excludes `adjustment`, `refund`, `redemption`, `exchange`).
- `RewardService` — `request_redemption` (hold coins + decrement stock + low-stock notification at 0/1), `approve` (stamp + digital-item credit), `reject` (refund coins + restore stock). Out-of-stock returns **409 Conflict** with `{detail, similar: [...]}`.
- `ExchangeService` — `request_exchange` (validate balance, snapshot rate, notify parents), `approve` (atomic debit `PaymentLedger` + credit `CoinLedger` + chronicle first-ever hook), `reject` (no ledger side-effects — money was never held).

## Exceptions
- `InsufficientCoinsError`, `InsufficientFundsError`, `RewardUnavailableError`.

## Gotchas
- **Wishlist restock fan-out**: when a parent edits a reward and stock crosses `0 → ≥1`, `RewardService` fans out `REWARD_RESTOCKED` notifications to every wishlist user and clears their wishlist rows in the same transaction.
- **Low-stock signal**: `request_redemption` fires `LOW_REWARD_STOCK` notification to parents the first time stock enters 0 or 1.
- **Coin boost whitelist**: when adding a new earn-kind `CoinLedger.Reason`, decide whether it belongs in `_BOOSTABLE_COIN_REASONS` (`apps/rpg/services.py`) and add a regression test in `apps/rpg/tests/test_boost_multipliers.py`.
- **`Reward.save()` defense-in-depth**: auto-attaches to default family when `family_id` is None (same pattern as `User`, `ProjectTemplate`, `Chore`).

## Key entry points
- `services.py` — `CoinService`, `RewardService`, `ExchangeService`.
- `models.py` — `CoinLedger.Reason` choices, `Reward.FulfillmentKind`, `RewardRedemption.Status`.
