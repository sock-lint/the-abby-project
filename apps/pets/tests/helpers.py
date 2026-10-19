"""Synthetic test setup still performs both authoritative incubation actions."""
from uuid import uuid4

from django.utils import timezone

from apps.pets.models import PetIncubation
from apps.pets.services import PetService


def hatch_ready_pet(user, egg_item_id, potion_item_id):
    incubation, _ = PetService.start_incubation(user, egg_item_id, potion_item_id, uuid4())
    PetIncubation.objects.filter(pk=incubation.pk).update(ready_at=timezone.now())
    return PetService.hatch_incubation(user, incubation.pk)[1]
