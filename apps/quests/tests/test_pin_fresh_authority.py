"""Native pins use the account returned by their row-lock admission."""
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.quests import goals
from apps.quests.models import (
    ChallengeContribution, ChallengeGoal, ChallengeOccurrence, ChallengePin,
)
from apps.rewards.models import CoinLedger
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NativePinFreshAuthorityTests(TestCase):
    def setUp(self):
        home = make_family(
            "Fresh native pin family", parents=[{"username": "fresh-pin-parent"}],
            children=[{"username": "fresh-pin-child"}],
        )
        self.parent, self.child = home.parents[0], home.children[0]
        self.other_family = make_family("Other fresh pin family").family
        self.occurrence = goals.create_goal(self.parent, self.child, {
            "user_id": self.child.pk, "name": "Three saved habits", "metric": "count",
            "target": Decimal("3"), "unit": "actions", "trigger_type": "habit_log",
            "period": "this_week", "coin_reward": 7,
        })

    @staticmethod
    def saved_state():
        return {model._meta.label: list(model.objects.order_by("pk").values()) for model in (
            ChallengeGoal, ChallengeOccurrence, ChallengeContribution, ChallengePin, CoinLedger,
        )}

    def assert_revoked_at_pin_lock(self, changes, *, clear=False):
        if clear:
            ChallengePin.objects.create(user=self.child, occurrence=self.occurrence)
        before = self.saved_state()
        acquire_lock = goals.lock_user

        def revoke_then_acquire(cached_user):
            # The request already resolved this account. Schedule the competing
            # account change immediately before its native lock reads the row.
            self.assertIs(cached_user, self.child)
            get_user_model().objects.filter(pk=cached_user.pk).update(**changes)
            locked_user = acquire_lock(cached_user)
            for field, value in changes.items():
                self.assertEqual(getattr(locked_user, field), value)
                self.assertNotEqual(getattr(cached_user, field), value)
            return locked_user

        with patch.object(goals, "lock_user", side_effect=revoke_then_acquire) as admission:
            with self.assertRaisesMessage(ValueError, "Challenge not found"):
                goals.set_pin(self.child, f"goal:{self.occurrence.pk}", clear=clear)
        admission.assert_called_once_with(self.child)
        self.assertEqual(self.saved_state(), before)

    def test_deactivated_account_cannot_create_pin_after_native_admission(self):
        self.assert_revoked_at_pin_lock({"is_active": False})

    def test_moved_account_cannot_create_pin_for_former_family(self):
        self.assert_revoked_at_pin_lock({"family_id": self.other_family.pk})

    def test_deactivated_account_cannot_clear_its_saved_pin(self):
        self.assert_revoked_at_pin_lock({"is_active": False}, clear=True)

    def test_moved_account_cannot_clear_its_former_family_pin(self):
        self.assert_revoked_at_pin_lock({"family_id": self.other_family.pk}, clear=True)
