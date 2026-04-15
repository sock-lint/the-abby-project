"""Regression test: ContentPack loader honors Badge.award_coins YAML field.

The loader's ``_load_badges`` must pass ``award_coins`` through to the
Badge row — default True when omitted, False when explicitly set.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase

from apps.achievements.models import Badge
from apps.rpg.content.loader import ContentPack


class LoaderBadgeAwardCoinsTests(TestCase):
    def _write_badge_pack(
        self, tmp: Path, *, name: str, include_award_coins: bool,
        award_coins_value: bool = False,
    ) -> Path:
        pack_dir = tmp / "testpack"
        pack_dir.mkdir()
        lines = [
            "badges:",
            f"  - name: {name}",
            "    description: test badge",
            "    criteria_type: quest_completed",
            "    criteria_value:",
            f"      quest_name: {name}",
            "    rarity: rare",
        ]
        if include_award_coins:
            lines.append(f"    award_coins: {str(award_coins_value).lower()}")
        (pack_dir / "badges.yaml").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
        return pack_dir

    def test_award_coins_defaults_true_when_omitted(self) -> None:
        name = "default-award-coins-badge"
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = self._write_badge_pack(
                Path(tmp), name=name, include_award_coins=False,
            )
            ContentPack(pack_dir).load(dry_run=False)

        badge = Badge.objects.get(name=name)
        self.assertTrue(
            badge.award_coins,
            "Omitting award_coins in YAML should default to True",
        )

    def test_award_coins_false_propagates(self) -> None:
        name = "silent-badge-no-coins"
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir = self._write_badge_pack(
                Path(tmp), name=name, include_award_coins=True,
                award_coins_value=False,
            )
            ContentPack(pack_dir).load(dry_run=False)

        badge = Badge.objects.get(name=name)
        self.assertFalse(
            badge.award_coins,
            "Setting award_coins: false in YAML must persist on the Badge row",
        )

    def test_re_load_updates_award_coins(self) -> None:
        """Flipping award_coins in YAML and re-loading updates the row."""
        name = "flipping-badge"
        with tempfile.TemporaryDirectory() as tmp:
            pack_dir_true = self._write_badge_pack(
                Path(tmp), name=name, include_award_coins=True,
                award_coins_value=True,
            )
            ContentPack(pack_dir_true).load(dry_run=False)
            self.assertTrue(Badge.objects.get(name=name).award_coins)

        with tempfile.TemporaryDirectory() as tmp:
            pack_dir_false = self._write_badge_pack(
                Path(tmp), name=name, include_award_coins=True,
                award_coins_value=False,
            )
            ContentPack(pack_dir_false).load(dry_run=False)
            self.assertFalse(Badge.objects.get(name=name).award_coins)
