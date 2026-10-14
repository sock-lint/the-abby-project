"""Local payout confirmation and statement reconciliation. No provider calls."""
import csv
import hashlib
import io
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from apps.timecards.models import Timecard
from .models import (
    GreenlightBalanceSnapshot, GreenlightStatementTransfer, GreenlightTransfer,
    PaymentLedger,
)
from .services import PaymentService

CSV_SCHEMA = ["date", "amount", "description", "reference", "type"]
MAX_CSV_BYTES = 512 * 1024
MAX_CSV_ROWS = 500
ZERO = Decimal("0.00")


class TransferConflict(APIException):
    status_code = 409
    default_code = "transfer_conflict"


def conflict(message):
    raise TransferConflict({"error": message})


def fail(message):
    raise ValidationError({"error": message})


def money(value, *, allow_zero=False, signed=False):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        fail("Invalid amount.")
    if not amount.is_finite() or amount.copy_abs() > Decimal("999999.99"):
        fail("Amount must be finite and no greater than $999,999.99.")
    if (not signed and amount < 0) or (not allow_zero and amount == 0):
        fail("Amount must be positive." if not allow_zero else "Amount must not be negative.")
    if amount != amount.quantize(Decimal("0.01")):
        fail("Amount must have at most two decimal places.")
    return amount.quantize(Decimal("0.01"))


def authorize_parent(parent, child):
    if parent.role != "parent" or child.role != "child" or not parent.family_id or parent.family_id != child.family_id:
        raise PermissionDenied("Only parents in this child's family can record payments.")


def lock_child(child):
    # This is the same first lock used by timecard generation/approval/payment.
    return get_user_model().objects.select_for_update().get(pk=child.pk)


def balances(child):
    owed = PaymentService.get_balance(child)
    # Withhold positive net hourly credits for each unapproved/orphan card.
    # Negative corrections cannot cancel a different card's withheld earnings.
    groups = PaymentLedger.objects.filter(
        user=child, entry_type=PaymentLedger.EntryType.HOURLY,
    ).exclude(timecard__status__in=[Timecard.Status.APPROVED, Timecard.Status.PAID]).values(
        "timecard_id",
    ).annotate(total=Sum("amount"))
    pending = sum((max(ZERO, group["total"]) for group in groups), ZERO)
    payable = max(ZERO, min(owed, owed - pending))
    return owed, payable, pending


def validate_payable(child, amount):
    payable = balances(child)[1]
    if amount > payable:
        fail(f"Amount exceeds the approved amount available to pay (${payable:.2f}).")


def payout_data(entry):
    try:
        transfer = entry.greenlight_transfer
    except GreenlightTransfer.DoesNotExist:
        transfer = None
    return {
        "id": entry.pk,
        "amount": f"{-entry.amount:.2f}",
        "transferred_on": transfer.transferred_on.isoformat() if transfer else None,
        "reference": transfer.reference if transfer else "",
        "memo": transfer.memo if transfer else entry.description,
        "timecard": entry.timecard_id,
        "source": transfer.source if transfer else "legacy",
        "reconciled": bool(transfer and GreenlightStatementTransfer.objects.filter(transfer=transfer).exists()),
        "created_by": transfer.created_by_id if transfer else entry.created_by_id,
        "created_at": (transfer.created_at if transfer else entry.created_at).isoformat(),
    }


def overview(child):
    from .serializers import GreenlightBalanceSnapshotSerializer

    owed, payable, pending = balances(child)
    snapshot = GreenlightBalanceSnapshot.objects.filter(user=child).first()
    cards = Timecard.objects.filter(
        user=child, status=Timecard.Status.APPROVED, total_earnings__gt=ZERO,
    ).exclude(
        payment_entries__entry_type=PaymentLedger.EntryType.PAYOUT,
    )
    payouts = PaymentLedger.objects.filter(
        user=child, entry_type=PaymentLedger.EntryType.PAYOUT,
    ).select_related("greenlight_transfer").order_by("-created_at", "-id")
    return {
        "user_id": child.pk,
        "owed_balance": f"{owed:.2f}",
        "approved_payable": f"{payable:.2f}",
        "pending_hourly": f"{pending:.2f}",
        "balance_snapshot": GreenlightBalanceSnapshotSerializer(snapshot).data if snapshot else None,
        "approved_timecards": [
            {"id": card.pk, "week_start": card.week_start.isoformat(), "total_earnings": f"{card.total_earnings:.2f}"}
            for card in cards
        ],
        "payouts": [payout_data(entry) for entry in payouts],
    }


def _same_confirmation(transfer, amount, transferred_on, reference, memo, timecard_id):
    return (
        transfer.amount == amount and transfer.transferred_on == transferred_on
        and transfer.reference == reference and transfer.memo == memo
        and transfer.payment_entry.timecard_id == timecard_id
    )


@transaction.atomic
def confirm_transfer(child, parent, *, amount, transferred_on, reference="", memo="", idempotency_key, timecard_id=None):
    authorize_parent(parent, child)
    child = lock_child(child)
    authorize_parent(parent, child)
    amount = money(amount)
    if transferred_on > timezone.localdate():
        fail("Transfer date must not be in the future.")
    existing = GreenlightTransfer.objects.filter(user=child, idempotency_key=idempotency_key).first()
    if existing:
        if not _same_confirmation(existing, amount, transferred_on, reference, memo, timecard_id):
            conflict("This confirmation key was already used for different transfer details.")
        return existing, False
    if reference:
        existing = GreenlightTransfer.objects.filter(user=child, reference=reference).first()
        if existing:
            if existing.amount != amount or existing.transferred_on != transferred_on or existing.payment_entry.timecard_id != timecard_id:
                conflict("This reference was already used for different transfer details.")
            return existing, False
    card = None
    if timecard_id is not None:
        card = Timecard.objects.select_for_update().filter(pk=timecard_id, user=child).first()
        if card is None:
            fail("Timecard not found for this child.")
        if card.status != Timecard.Status.APPROVED or PaymentLedger.objects.filter(
            timecard=card, entry_type=PaymentLedger.EntryType.PAYOUT,
        ).exists():
            fail("Choose an approved timecard that has not already been paid.")
        if amount != card.total_earnings:
            fail("A timecard transfer must equal that timecard's full total.")
    validate_payable(child, amount)
    entry = PaymentService.record_entry(
        child, -amount, PaymentLedger.EntryType.PAYOUT,
        description=memo or f"Confirmed Greenlight transfer on {transferred_on}",
        timecard=card, created_by=parent,
    )
    transfer = GreenlightTransfer.objects.create(
        user=child, payment_entry=entry, amount=amount, transferred_on=transferred_on,
        reference=reference, memo=memo, source=GreenlightTransfer.Source.MANUAL,
        idempotency_key=idempotency_key, created_by=parent,
    )
    if card is not None:
        card.status = Timecard.Status.PAID
        card.save(update_fields=["status", "updated_at"])
    return transfer, True


def _fingerprint(transaction_type, transferred_on, amount, description, reference):
    # A reference identifies the transaction even when exported descriptions
    # change. Amount/date are validated separately when reusing that reference.
    identity = [transaction_type, reference] if reference else [
        transaction_type, transferred_on.isoformat(), f"{amount:.2f}", " ".join(description.split()),
    ]
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def parse_statement(csv_data):
    if not isinstance(csv_data, str) or not csv_data.strip():
        fail("csv_data is required.")
    if len(csv_data.encode("utf-8")) > MAX_CSV_BYTES:
        fail("CSV must be no larger than 512 KiB.")
    reader = csv.DictReader(io.StringIO(csv_data.lstrip("\ufeff")), strict=True)
    try:
        if reader.fieldnames != CSV_SCHEMA:
            fail("Use the documented CSV header: date,amount,description,reference,type.")
        rows = []
        for number, raw in enumerate(reader, start=1):
            if number > MAX_CSV_ROWS:
                fail("CSV must contain no more than 500 data rows.")
            row = {
                "row_number": number, "fingerprint": None,
                "transaction_type": str(raw.get("type") or "").strip().lower(),
                "date": str(raw.get("date") or "").strip(),
                "amount": str(raw.get("amount") or "").strip(),
                "description": str(raw.get("description") or "").strip(),
                "reference": str(raw.get("reference") or "").strip(),
                "eligible": False, "error": None, "duplicate": False, "match_candidates": [],
            }
            if row["transaction_type"] == "transfer" and row["reference"] and len(row["reference"]) <= 200:
                # Preserve a referenced identity even if another field is bad,
                # so a later valid repeat cannot hide the malformed conflict.
                row["fingerprint"] = _fingerprint("transfer", None, None, "", row["reference"])
            try:
                if None in raw or any(raw.get(key) is None for key in CSV_SCHEMA):
                    fail("Row does not have exactly five columns.")
                if len(row["description"]) > 1000 or len(row["reference"]) > 200:
                    fail("Description or reference is too long.")
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["date"]):
                    fail("Date must use YYYY-MM-DD.")
                transferred_on = date.fromisoformat(row["date"])
                if transferred_on > timezone.localdate():
                    fail("Transfer date must not be in the future.")
                amount = money(row["amount"], signed=row["transaction_type"] != "transfer", allow_zero=True)
                row["amount"] = f"{amount:.2f}"
                if row["transaction_type"] == "transfer":
                    money(amount)
                    row["eligible"] = True
                    row["fingerprint"] = _fingerprint("transfer", transferred_on, amount, row["description"], row["reference"])
            except (ValidationError, ValueError) as exc:
                row["error"] = str(exc.detail["error"]) if isinstance(exc, ValidationError) else "Invalid date."
            rows.append(row)
    except csv.Error:
        fail("Malformed CSV.")
    # Poison the entire identity, including a later repeat of the first row.
    # A dict lookup must never conceal a conflicting earlier reference.
    grouped = {}
    for row in rows:
        if row["fingerprint"]:
            grouped.setdefault(row["fingerprint"], []).append(row)
    for group in grouped.values():
        if len({(row["date"], row["amount"]) for row in group}) > 1 or (len(group) > 1 and any(row["error"] for row in group)):
            for row in group:
                row["eligible"] = False
                row["error"] = "Conflicting rows reuse the same transfer reference with different dates or amounts."
        elif len(group) > 1:
            for row in group[1:]:
                row["duplicate"] = True
    return rows


def _existing_statement(child, row):
    if not row["fingerprint"]:
        return None
    return GreenlightStatementTransfer.objects.filter(user=child, fingerprint=row["fingerprint"]).first()


def _matches(transfer, row):
    return transfer.amount == Decimal(row["amount"]) and transfer.transferred_on.isoformat() == row["date"]


def preview_statement(child, csv_data):
    rows = parse_statement(csv_data)
    seen = set()
    payouts = list(PaymentLedger.objects.filter(
        user=child, entry_type=PaymentLedger.EntryType.PAYOUT,
    ).select_related("greenlight_transfer"))
    for row in rows:
        if not row["eligible"]:
            continue
        prior = _existing_statement(child, row)
        if prior and (prior.amount != Decimal(row["amount"]) or prior.transferred_on.isoformat() != row["date"]):
            row["error"] = "This reference was already reconciled with a different date or amount."
            row["eligible"] = False
            continue
        row["duplicate"] = row["duplicate"] or prior is not None or row["fingerprint"] in seen
        seen.add(row["fingerprint"])
        for entry in payouts:
            if -entry.amount != Decimal(row["amount"]):
                continue
            try:
                transfer = entry.greenlight_transfer
            except GreenlightTransfer.DoesNotExist:
                transfer = None
            if transfer:
                if GreenlightStatementTransfer.objects.filter(transfer=transfer).exists():
                    continue
                if not _matches(transfer, row):
                    continue
                if transfer.reference and transfer.reference != row["reference"]:
                    continue
            row["match_candidates"].append(entry.pk)
        if row["reference"]:
            transfer = GreenlightTransfer.objects.filter(user=child, reference=row["reference"]).first()
            if transfer and not _matches(transfer, row):
                row["error"] = "This reference was already recorded with a different date or amount."
                row["eligible"] = False
    return {"rows": rows, "schema": CSV_SCHEMA}


def _match_existing(child, parent, row, payment_id):
    entry = PaymentLedger.objects.filter(
        pk=payment_id, user=child, entry_type=PaymentLedger.EntryType.PAYOUT,
    ).first()
    if entry is None or -entry.amount != Decimal(row["amount"]):
        fail("The selected payout must belong to this child and have the same amount.")
    try:
        transfer = entry.greenlight_transfer
    except GreenlightTransfer.DoesNotExist:
        transfer = None
    if transfer is not None:
        if not _matches(transfer, row) or (transfer.reference and transfer.reference != row["reference"]):
            fail("The selected payout has a different transfer date or reference.")
        if GreenlightStatementTransfer.objects.filter(transfer=transfer).exists():
            fail("The selected payout is already matched to another statement row.")
        if not transfer.reference and row["reference"]:
            transfer.reference = row["reference"]
            transfer.save(update_fields=["reference"])
        return transfer
    return GreenlightTransfer.objects.create(
        user=child, payment_entry=entry, amount=Decimal(row["amount"]),
        transferred_on=date.fromisoformat(row["date"]), reference=row["reference"],
        memo=entry.description, source=GreenlightTransfer.Source.STATEMENT,
        idempotency_key=f"statement:{row['fingerprint']}", created_by=parent,
    )


@transaction.atomic
def reconcile_statement(child, parent, csv_data, selections):
    authorize_parent(parent, child)
    child = lock_child(child)
    authorize_parent(parent, child)
    rows = parse_statement(csv_data)
    by_fingerprint = {row["fingerprint"]: row for row in rows if row["fingerprint"]}
    if not selections:
        fail("Select at least one transfer row to reconcile.")
    result = {"recorded": 0, "matched": 0, "duplicates": 0}
    seen = set()
    for selection in selections:
        fingerprint = selection["fingerprint"]
        if fingerprint in seen:
            fail("Select each transfer row only once.")
        seen.add(fingerprint)
        row = by_fingerprint.get(fingerprint)
        if row is None or not row["eligible"] or row["error"]:
            fail("Selected row is not a valid transfer in this CSV.")
        prior = _existing_statement(child, row)
        if prior:
            if prior.amount != Decimal(row["amount"]) or prior.transferred_on.isoformat() != row["date"]:
                conflict("This reference was already reconciled with a different date or amount.")
            payment_id = selection.get("match_payment_id")
            timecard_id = selection.get("timecard_id")
            if (payment_id is not None and payment_id != prior.transfer.payment_entry_id) or (
                timecard_id is not None and timecard_id != prior.transfer.payment_entry.timecard_id
            ):
                fail("The previously reconciled row is associated with a different payout.")
            result["duplicates"] += 1
            continue
        payment_id = selection.get("match_payment_id")
        timecard_id = selection.get("timecard_id")
        if payment_id is not None and timecard_id is not None:
            fail("Choose an existing payout or a new timecard transfer, not both.")
        existing_reference = GreenlightTransfer.objects.filter(user=child, reference=row["reference"]).first() if row["reference"] else None
        if existing_reference and not _matches(existing_reference, row):
            conflict("This reference was already recorded with a different date or amount.")
        if existing_reference and (payment_id != existing_reference.payment_entry_id):
            fail("This reference already belongs to a payout. Select that payout to match it.")
        if payment_id is not None:
            transfer = _match_existing(child, parent, row, payment_id)
            result["matched"] += 1
        else:
            transfer, created = confirm_transfer(
                child, parent, amount=row["amount"], transferred_on=date.fromisoformat(row["date"]),
                reference=row["reference"], memo=row["description"],
                idempotency_key=f"statement:{fingerprint}", timecard_id=timecard_id,
            )
            if not created:
                fail("This payout was already recorded. Match it explicitly instead.")
            transfer.source = GreenlightTransfer.Source.STATEMENT
            transfer.save(update_fields=["source"])
            result["recorded"] += 1
        GreenlightStatementTransfer.objects.create(
            user=child, fingerprint=fingerprint, transfer=transfer,
            transferred_on=date.fromisoformat(row["date"]), amount=Decimal(row["amount"]),
            description=row["description"], reference=row["reference"], created_by=parent,
        )
    return result
