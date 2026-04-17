from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.quests.serializers import QuestWriteSerializer
from apps.quests.validators import validate_trigger_filter


class ValidateTriggerFilterTests(TestCase):
    def test_empty_or_none_is_valid(self):
        # No filter means "match every trigger" — the common case.
        validate_trigger_filter(None)
        validate_trigger_filter({})

    def test_non_dict_is_rejected(self):
        with self.assertRaises(ValidationError):
            validate_trigger_filter(["chore_complete"])
        with self.assertRaises(ValidationError):
            validate_trigger_filter("allowed_triggers=chore_complete")

    def test_typo_in_key_is_rejected(self):
        # The whole point of this validator: a typo like the missing 's'
        # below used to silently accept every trigger.
        with self.assertRaises(ValidationError) as ctx:
            validate_trigger_filter({"allowed_trigger": ["chore_complete"]})
        self.assertIn("allowed_trigger", str(ctx.exception))

    def test_unknown_trigger_value_is_rejected(self):
        with self.assertRaises(ValidationError) as ctx:
            validate_trigger_filter({"allowed_triggers": ["chore_compelte"]})
        self.assertIn("chore_compelte", str(ctx.exception))

    def test_allowed_triggers_must_be_list(self):
        with self.assertRaises(ValidationError):
            validate_trigger_filter({"allowed_triggers": "chore_complete"})

    def test_accepts_known_keys_and_values(self):
        # Documented-but-unimplemented keys still pass — the validator is
        # forward-compatible so content packs can reference them.
        validate_trigger_filter({
            "allowed_triggers": ["chore_complete", "homework_complete"],
            "project_id": 42,
            "skill_category_id": 7,
            "chore_ids": [1, 2, 3],
            "on_time": True,
            "savings_goal_id": 9,
            "streak_target": 7,
            "perfect_day_target": 3,
        })


class QuestWriteSerializerTriggerFilterTests(TestCase):
    """End-to-end wiring: bad trigger_filter in API payload returns 400."""

    def _payload(self, **overrides):
        base = {
            "name": "Test Quest",
            "description": "A test quest",
            "quest_type": "boss",
            "target_value": 100,
            "duration_days": 7,
        }
        base.update(overrides)
        return base

    def test_serializer_rejects_unknown_trigger_filter_key(self):
        serializer = QuestWriteSerializer(data=self._payload(
            trigger_filter={"allowed_trigger": ["chore_complete"]},
        ))
        self.assertFalse(serializer.is_valid())
        self.assertIn("trigger_filter", serializer.errors)

    def test_serializer_accepts_valid_trigger_filter(self):
        serializer = QuestWriteSerializer(data=self._payload(
            trigger_filter={"allowed_triggers": ["chore_complete"]},
        ))
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_serializer_accepts_empty_trigger_filter(self):
        serializer = QuestWriteSerializer(data=self._payload())
        self.assertTrue(serializer.is_valid(), serializer.errors)
