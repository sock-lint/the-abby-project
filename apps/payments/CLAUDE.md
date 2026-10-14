# apps/payments/

The append-only `PaymentLedger` tracks money the parent owes the child. Positive
entries accrue earnings; negative payouts settle that debt. It is never a live
Greenlight account balance. Non-monetary Coins remain in `apps/rewards`.

## Greenlight bookkeeping

`greenlight.py` and `greenlight_views.py` implement local confirmation and
reconciliation. They do not connect to Greenlight, initiate transfers, collect
Greenlight credentials, or claim compatibility with a native provider export.

- `GreenlightTransfer` records the confirmed amount, actual transfer date,
  optional reference/memo, parent, source, retry key and one linked payout ledger
  entry. Keys and nonblank references are unique per child. A reused key with
  changed details, or reused reference with a different date/amount/card, is HTTP
  409. A compatible repeat returns the original payout without another debit.
- `GreenlightBalanceSnapshot` is an append-only parent observation with an
  explicit `as_of` timestamp. The most recent observation by `as_of`, then ID,
  appears in overview. Transfers never change its value; spending is unknown.
- `GreenlightStatementTransfer` preserves the selected row, fingerprint,
  date/reference/description and reconciling parent. One statement row can claim
  one transfer, and one transfer cannot be claimed by different rows.
- New payouts lock the child before checking current payable funds and writing.
  Pending/disputed/unlinked hourly credits are withheld, with positive net
  credits calculated per card; approved payable is clamped to zero and never
  exceeds the signed owed balance. Other authorized ledger earnings are payable.
  Money-to-Coins approval uses the same user lock before its balance check/debit.
- A timecard-associated Greenlight confirmation requires an approved, unpaid
  card and its exact full amount. It atomically writes the payout and paid status.
  Existing timecard `mark-paid` uses the same current-payable guard for its first
  debit, requires approval/full total, preserves existing-payout retry safety,
  and can repair a paid legacy card when its earned balance remains available.
  Generic confirmations remain unallocated: select the card when paying a week.
  Current-payable checks prevent later routes from overdrawing settled earnings.

## API

All routes below are under `/api/payments/greenlight/`. Money is serialized as a
decimal string. Parent writes require `user_id` for a child in their family.
Children can read only their own overview. No mutation is available to children.

- `GET overview/?user_id=ID`: `user_id`, `owed_balance`, `approved_payable`,
  `pending_hourly`, nullable `balance_snapshot`, `approved_timecards`, `payouts`.
  `approved_timecards` includes only approved, unpaid cards with positive totals;
  nonpositive cards retain their approval without a payment or payout ledger row.
  Child requests may omit `user_id`. Payout amounts are positive display values;
  `id` is the linked ledger ID, and `transferred_on` is null for legacy entries
  without recorded external metadata. Legacy dates are unknown, so matching
  them always requires an explicit parent choice. `source` is `manual`,
  `statement` or `legacy`; `reconciled` indicates a saved statement match.
- `POST payout/`: `user_id`, positive `amount`, historical `transferred_on`
  (YYYY-MM-DD), `idempotency_key`, optional `reference`, `memo`, `timecard_id`.
  Returns `{created, payout}` (201 when new, 200 on a compatible retry).
- `POST snapshot/`: `user_id`, nonnegative `amount`, historical `as_of` (ISO
  timestamp), optional `memo`. Returns `id`, `user`, `amount`, `as_of`, `memo`,
  `created_by`, `created_at` (201).
- `POST preview/`: `user_id`, `csv_data`. Returns `schema` and `rows` with
  `row_number`, `fingerprint`, `transaction_type`, `date`, `amount`, `description`,
  `reference`, `eligible`, `error`, `duplicate`, `match_candidates` (ledger IDs).
  Preview performs no database writes.
- `POST reconcile/`: the same `user_id`, original `csv_data`, and explicit
  `selections: [{fingerprint, match_payment_id?, timecard_id?}]`. Omit ignored
  rows. Each selection either records a new transfer or matches one existing
  payout; choosing both matching and a new card is rejected. All selected rows
  commit atomically, and retries count previously reconciled rows as duplicates.
  Returns `{recorded, matched, duplicates}`. Preview and commit both revalidate
  the original text rather than trusting client-provided amounts.

Compatibility: `/api/payments/payout/` now requires the same confirmation payload
and uses the new payout response. `/api/greenlight/import/` is preview-only and
requires the documented schema; it cannot blindly deduct imported transactions.

## Canonical CSV

Header and order must be exactly `date,amount,description,reference,type`:

```csv
date,amount,description,reference,type
2026-10-05,12.50,Weekly project earnings,external-transfer-123,transfer
2026-10-06,-3.00,Book purchase,external-purchase-456,purchase
```

Dates use YYYY-MM-DD, amounts use signed plain decimal dollars with at most two
places (no dollar signs or thousands separators), and only positive `transfer`
rows are eligible. Purchases and other credit types are ignored. The parent must
normalize any source export to this schema; a native Greenlight format is not
assumed. Limit: 512 KiB and 500 data rows; memo/description 1000 characters,
reference 200 characters. Invalid/missing/extra cells and malformed CSV are
reported or rejected before any commit.

A nonblank reference identifies a transaction per child even when description
formatting changes; differing dates/amounts under that reference conflict. A
reference-less fingerprint uses date, amount and whitespace-normalized
description. Identical same-day rows conservatively deduplicate: legitimate
identical transfers need distinct real references. Never auto-select rows or
auto-match suggestions. Matching an existing manual/timecard payout explicitly
preserves the original debit instead of creating another one.

## Validation

`python manage.py test --settings=config.settings_test apps.payments apps.timecards`
with a disposable SQLite `DATABASE_URL` and synthetic `SECRET_KEY` covers family
permissions, validation, confirmation keys/references, preview-only behavior,
explicit matching, atomic rollback and old-route safety. PostgreSQL also runs
`test_greenlight_concurrency` and timecard concurrency checks using real row
locks; those checks intentionally skip under SQLite. Shared real-response
fixtures are in `contracts/api`, with their backend harness under `config/tests`.
