"""Saved forecasts must detect changes to fixed XP destination resolution."""
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.achievements import source_identity
from apps.chronicle import services as chronicle_services
from apps.reading.services import ReadingRewardService
from apps.rpg.progression import engine


class FixedXPRulesFingerprintTests(SimpleTestCase):
    def assert_source_change_invalidates(self, target):
        before = engine.rules_fingerprint()
        original = engine.inspect.getsource

        def changed_source(obj):
            source = original(obj)
            return source + "\n# changed XP destination policy\n" if obj == target else source

        with patch.object(engine.inspect, "getsource", side_effect=changed_source):
            self.assertNotEqual(before, engine.rules_fingerprint())

    def test_journal_destination_changes_invalidate_saved_forecasts(self):
        self.assert_source_change_invalidates(chronicle_services._journal_xp_tags)

    def test_reading_destination_changes_invalidate_saved_forecasts(self):
        self.assert_source_change_invalidates(ReadingRewardService._reading_skill)

    def test_shared_resolver_changes_invalidate_saved_forecasts(self):
        self.assert_source_change_invalidates(source_identity)

    def test_reading_identity_wrapper_changes_invalidate_saved_forecasts(self):
        self.assert_source_change_invalidates(ReadingRewardService._source_identity)
