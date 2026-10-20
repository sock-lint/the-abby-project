"""Install a small starter routine without replacing family choices."""
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.habits.models import Habit


@transaction.atomic
def ensure_starter_habits(child, *, created_by=None):
    """Install once at onboarding or seed time; reads never call this.

    A stable key survives renames and pauses. Legacy twice-daily teeth habits
    retain their name, rewards, history and active state when adopted.
    """
    child = User.objects.select_for_update(no_key=True).get(pk=child.pk)
    if child.role != "child":
        return []
    if created_by is not None:
        created_by = User.objects.filter(
            pk=created_by.pk, family_id=child.family_id, role="parent",
        ).first()
        if created_by is None:
            raise ValueError("Starter routines must be created by a parent in the child's family.")
    existing = Habit.objects.filter(user=child, starter_key="brush_teeth").first()
    if existing is not None:
        return [existing]

    legacy = Habit.objects.filter(
        Q(name__iexact="Brush teeth") | Q(name__iexact="Brush your teeth"),
        user=child, starter_key__isnull=True, habit_type="positive",
        max_taps_per_day=2, pending_parent_review=False,
    ).order_by("pk").first()
    if legacy is not None:
        legacy.starter_key = "brush_teeth"
        legacy.save(update_fields=["starter_key"])
        return [legacy]

    if created_by is None:
        created_by = User.objects.filter(
            family_id=child.family_id, role="parent", is_active=True,
        ).order_by("pk").first() or child
    return [Habit.objects.create(
        user=child, created_by=created_by, starter_key="brush_teeth",
        name="Brush your teeth", icon="🪥", habit_type="positive",
        max_taps_per_day=2, xp_reward=5, pending_parent_review=False,
    )]
