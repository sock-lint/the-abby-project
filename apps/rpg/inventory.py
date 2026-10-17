"""Shared stack grants coordinated with inventory consumption."""

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import UserInventory


@transaction.atomic
def grant_item(user, item, quantity=1):
    """Add a caller-validated reward while holding the stack until commit.

    Consumption can delete the last unit. Lock the lookup so an existing
    stack cannot disappear before its increment, and use database arithmetic
    so grants preserve every committed increment.
    """
    inventory, created = UserInventory.objects.select_for_update().get_or_create(
        user=user, item=item, defaults={"quantity": quantity},
    )
    if not created:
        UserInventory.objects.filter(pk=inventory.pk).update(
            quantity=F("quantity") + quantity, updated_at=timezone.now(),
        )
