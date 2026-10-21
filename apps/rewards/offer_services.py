"""Shared parent shop edits, including complete wishlist restock behavior."""
import logging

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404

from apps.accounts.models import User
from apps.notifications.models import NotificationType
from apps.notifications.services import notify

from .availability import reward_is_available
from .models import Reward, RewardWishlist
from .serializers import RewardWriteSerializer

logger = logging.getLogger(__name__)


def notify_wishlist_on_restock(reward):
    """Notify each eligible saved bookmark once, retaining retired bookmarks."""
    if not reward.is_active or not reward_is_available(reward):
        return
    from django.conf import settings
    from django.core.mail import send_mail

    users = User.objects.filter(reward_wishlist_entries__reward=reward).distinct()
    for user in users:
        notify(user, title=f"Back in stock: {reward.name}",
               message=f'"{reward.name}" is available again — head to the rewards shelf to redeem.',
               notification_type=NotificationType.REWARD_RESTOCKED, link="/rewards")
        if user.email:
            try:
                send_mail(
                    subject=f"Back in stock: {reward.name}",
                    message=(f"Hi {user.display_label}!\n\n"
                             f'"{reward.name}" from your wishlist is available '
                             f"again ({reward.cost_coins} coins). Head to the "
                             "rewards shelf to redeem it before it sells out.\n"),
                    from_email=settings.DEFAULT_FROM_EMAIL, recipient_list=[user.email],
                )
            except Exception:
                logger.exception("Failed to send restock email to user %s for reward %s", user.pk, reward.pk)
    RewardWishlist.objects.filter(reward=reward).delete()


@transaction.atomic
def update_reward_offer(actor, reward_id, data, *, serializer_class=RewardWriteSerializer, context=None, partial=True):
    """Read the authoritative offer under its reservation lock, then edit once."""
    if actor.role != "parent" or not actor.is_active:
        raise PermissionDenied("Shop edits require an active parent.")
    reward = get_object_or_404(
        Reward.objects.select_for_update(no_key=True), pk=reward_id, family_id=actor.family_id,
    )
    serializer = serializer_class(reward, data=data, partial=partial, context=context or {})
    serializer.is_valid(raise_exception=True)
    name = serializer.validated_data.get("name", reward.name)
    if Reward.objects.filter(name=name, family_id=actor.family_id).exclude(pk=reward.pk).exists():
        raise ValidationError({"name": "Another reward already has this name."})
    previous_stock = reward.stock
    reward = serializer.save()
    if previous_stock == 0 and reward.stock is not None and reward.stock >= 1:
        notify_wishlist_on_restock(reward)
    return reward
