"""Shared reading writes, saved summaries and once-daily RPG rewards."""
import json
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.achievements.models import Skill
from apps.achievements.services import AwardService
from apps.notifications.services import defer_push_until_commit
from apps.quests.activity import household_timezone
from apps.rewards.models import CoinLedger
from apps.rpg.constants import TriggerType
from apps.rpg.services import GameLoopService

from .models import ReadingBook, ReadingDailyReward, ReadingRewardCredit, ReadingSession


def lock_reading_owner(target, requester):
    """Serialize every reading write and recheck ownership after waiting."""
    target = (
        get_user_model().objects.select_for_update(no_key=True, of=("self",))
        .select_related("family")
        .filter(pk=target.pk, role="child", family_id=requester.family_id)
        .first()
    )
    if target is None:
        raise NotFound("Child not found.")
    return target


def reading_payload(data):
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))


def _create_details(validated_data):
    values = dict(validated_data)
    values.pop("user_id", None)
    request_id = values.pop("client_request_id")
    payload = reading_payload(values)
    return values, request_id, payload


def _existing_request(model, target, request_id, payload):
    existing = model.objects.filter(user=target, client_request_id=request_id).first()
    if existing is not None and existing.create_payload != payload:
        raise ValidationError({"client_request_id": "This request was already saved with different details."})
    return existing


@transaction.atomic
def create_reading_book(requester, target, validated_data):
    """Save shared-serializer data once; identical retries return current state."""
    values, request_id, payload = _create_details(validated_data)
    target = lock_reading_owner(target, requester)
    book = _existing_request(ReadingBook, target, request_id, payload)
    created = book is None
    if created:
        book = ReadingBook.objects.create(
            user=target, client_request_id=request_id, create_payload=payload, **values,
        )
    return book, created


@transaction.atomic
def create_reading_session(requester, target, validated_data):
    """Save and credit a new session in the same transaction for REST and MCP."""
    values, request_id, payload = _create_details(validated_data)
    book_id = values.pop("book")
    target = lock_reading_owner(target, requester)
    session = _existing_request(ReadingSession, target, request_id, payload)
    created = session is None
    if created:
        book = ReadingBook.objects.filter(pk=book_id, user=target).first()
        if book is None:
            raise ValidationError({"book": "Choose a book from this reader's shelf."})
        # Default only after constructing the retry identity: an omitted date
        # still identifies the original request when a client retries tomorrow.
        values.setdefault("occurred_on", timezone.localdate(timezone=household_timezone(target)))
        session = ReadingSession.objects.create(
            user=target, book=book, client_request_id=request_id, create_payload=payload, **values,
        )
        ReadingRewardService.credit_new_session(target, session)
    return session, created


def reading_summary(target):
    """Project saved history and actual daily credit without creating records."""
    books = ReadingBook.objects.filter(user=target).aggregate(
        books_total=Count("id"), books_finished=Count("id", filter=Q(status=ReadingBook.Status.FINISHED)),
    )
    sessions = ReadingSession.objects.filter(user=target).aggregate(
        sessions_total=Count("id"), total_minutes=Sum("duration_minutes", default=0),
        total_pages=Sum("pages_read", default=0),
    )
    tz = household_timezone(target)
    day = timezone.localdate(timezone=tz)
    return {
        **books, **sessions, "today": day.isoformat(), "timezone": str(tz),
        "reading_adventure": ReadingRewardService.daily_payload(target, day=day),
    }


class ReadingRewardService:
    TARGET_MINUTES = 10
    BASE_XP = 15
    BASE_COINS = 5
    SKILL_NAME = "Reading Comprehension"

    @classmethod
    @transaction.atomic
    def credit_new_session(cls, user, session):
        """Credit one genuinely new, present-day session under the owner lock.

        Call only immediately after insertion, never for a replay or PATCH.
        Progress remains separate from mutable session history. The caller's
        transaction also contains the inserted session, so a payout failure
        leaves the same request eligible for an ordinary retry.
        """
        get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
        if session.user_id != user.pk:
            return
        credit, created = ReadingRewardCredit.objects.get_or_create(
            user=user, client_request_id=session.client_request_id,
            defaults={"day": session.occurred_on, "minutes": 0},
        )
        # Even a zero-minute, historical or over-cap request keeps its original
        # classification after deletion. Retrying tomorrow cannot turn it into
        # a fresh reward opportunity.
        if not created:
            return
        day = timezone.localdate(timezone=household_timezone(user))
        if session.occurred_on != day or session.duration_minutes <= 0:
            return
        daily, _ = ReadingDailyReward.objects.select_for_update().get_or_create(user=user, day=day)
        if daily.awarded_at is not None:
            return
        added_minutes = min(cls.TARGET_MINUTES - daily.minutes_credited, session.duration_minutes)
        credit.minutes = added_minutes
        credit.save(update_fields=["minutes"])
        daily.minutes_credited += added_minutes
        if daily.minutes_credited < cls.TARGET_MINUTES:
            daily.save(update_fields=["minutes_credited", "updated_at"])
            return

        skill = Skill.objects.filter(name=cls.SKILL_NAME, category__name="Language Arts").first()
        tags = [SimpleNamespace(skill=skill, xp_weight=1)] if skill is not None else []
        # Observe only entries created by this direct reading award. Badge,
        # check-in and drop Coins have their own reasons and receipts.
        prior_coin_id = CoinLedger.objects.filter(user=user, reason=CoinLedger.Reason.READING).aggregate(
            last_id=Max("pk"),
        )["last_id"] or 0
        with defer_push_until_commit():
            award = AwardService.grant(
                user, xp_tags=tags, xp=cls.BASE_XP, xp_source_label="Reading adventure",
                coins=cls.BASE_COINS, coin_reason=CoinLedger.Reason.READING,
                coin_description="Daily reading adventure", badge_scopes={"skill_xp", "coin", "badges"},
            )
            daily.xp_awarded = award["xp_awarded"]
            daily.coins_awarded = CoinLedger.objects.filter(
                user=user, reason=CoinLedger.Reason.READING, pk__gt=prior_coin_id,
            ).aggregate(total=Sum("amount", default=0))["total"]
            daily.source_session = session
            daily.awarded_at = timezone.now()
            daily.save(update_fields=[
                "minutes_credited", "xp_awarded", "coins_awarded", "source_session", "awarded_at", "updated_at",
            ])
            # Other task flows tolerate a failed optional step. This reward is
            # one transaction; pushes must not escape a later strict rollback.
            GameLoopService.on_task_completed(
                user, TriggerType.READING_LOGGED,
                {"session_id": session.pk, "reading_reward_id": daily.pk}, strict=True,
            )

    @classmethod
    def daily_payload(cls, user, *, day=None):
        """Read current progress without creating a receipt or awarding."""
        if day is None:
            day = timezone.localdate(timezone=household_timezone(user))
        daily = ReadingDailyReward.objects.filter(user=user, day=day).first()
        minutes = daily.minutes_credited if daily else 0
        return {
            "day": day.isoformat(), "target_minutes": cls.TARGET_MINUTES,
            "minutes_credited": minutes, "remaining_minutes": max(0, cls.TARGET_MINUTES - minutes),
            "earned": bool(daily and daily.awarded_at), "base_xp": cls.BASE_XP, "base_coins": cls.BASE_COINS,
            "xp_awarded": daily.xp_awarded if daily else 0, "coins_awarded": daily.coins_awarded if daily else 0,
            "skill_name": cls.SKILL_NAME,
        }
