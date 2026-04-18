"""Tests for the draft_pack_entries MCP tool.

Covers append-mode merge dedup by natural key, replace-mode overwrite,
parent-only gating, and rejection of entries missing their natural key.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import yaml
from django.test import TestCase, override_settings
from pydantic import ValidationError as PydanticValidationError

from apps.accounts.models import User
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import MCPPermissionDenied, MCPValidationError
from apps.mcp_server.schemas import DraftPackEntriesIn
from apps.mcp_server.tools import content_packs as cp


_VALIDATION_ERRORS = (MCPValidationError, PydanticValidationError)


class _PacksMixin(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.tmp = Path(tempfile.mkdtemp(prefix="mcp_draft_test_"))
        self._override = override_settings(BASE_DIR=str(self.tmp))
        self._override.enable()
        (self.tmp / "content" / "rpg" / "packs").mkdir(parents=True)

    def tearDown(self) -> None:
        self._override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def _pack_file(self, pack: str, filename: str) -> Path:
        return self.tmp / "content" / "rpg" / "packs" / pack / filename


class DraftPackEntriesAppendTests(_PacksMixin):
    def test_append_creates_file_when_missing(self) -> None:
        with override_user(self.parent):
            result = cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="items.yaml",
                entries=[{
                    "slug": "spring-apple",
                    "name": "Spring Apple",
                    "item_type": "food",
                    "sprite_key": "apple",
                }],
            ))
        self.assertEqual(result["entry_count"], 1)
        path = self._pack_file("spring", "items.yaml")
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertEqual(len(parsed["items"]), 1)
        self.assertEqual(parsed["items"][0]["slug"], "spring-apple")

    def test_append_dedupes_by_slug_last_wins(self) -> None:
        with override_user(self.parent):
            cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="items.yaml",
                entries=[
                    {"slug": "a", "name": "A-v1", "item_type": "food"},
                    {"slug": "b", "name": "B", "item_type": "food"},
                ],
            ))
            result = cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="items.yaml",
                entries=[
                    {"slug": "a", "name": "A-v2", "item_type": "food"},
                    {"slug": "c", "name": "C", "item_type": "food"},
                ],
            ))
        self.assertEqual(result["entry_count"], 3)
        parsed = yaml.safe_load(
            self._pack_file("spring", "items.yaml").read_text(encoding="utf-8"),
        )
        by_slug = {e["slug"]: e for e in parsed["items"]}
        self.assertEqual(by_slug["a"]["name"], "A-v2")
        self.assertEqual(set(by_slug), {"a", "b", "c"})

    def test_badges_dedupes_by_name(self) -> None:
        with override_user(self.parent):
            cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="badges.yaml",
                entries=[{
                    "name": "Gardener",
                    "description": "v1",
                    "criteria_type": "projects_completed",
                    "criteria_value": 1,
                }],
            ))
            cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="badges.yaml",
                entries=[{
                    "name": "Gardener",
                    "description": "v2",
                    "criteria_type": "projects_completed",
                    "criteria_value": 5,
                }],
            ))
        parsed = yaml.safe_load(
            self._pack_file("spring", "badges.yaml").read_text(encoding="utf-8"),
        )
        self.assertEqual(len(parsed["badges"]), 1)
        self.assertEqual(parsed["badges"][0]["description"], "v2")

    def test_replace_mode_overwrites(self) -> None:
        with override_user(self.parent):
            cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="items.yaml",
                entries=[
                    {"slug": "a", "name": "A", "item_type": "food"},
                    {"slug": "b", "name": "B", "item_type": "food"},
                ],
            ))
            result = cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="items.yaml",
                mode="replace",
                entries=[{"slug": "only", "name": "Only", "item_type": "food"}],
            ))
        self.assertEqual(result["entry_count"], 1)
        parsed = yaml.safe_load(
            self._pack_file("spring", "items.yaml").read_text(encoding="utf-8"),
        )
        self.assertEqual(
            [e["slug"] for e in parsed["items"]], ["only"],
        )


class DraftPackEntriesSafetyTests(_PacksMixin):
    def test_child_blocked(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="items.yaml",
                entries=[{"slug": "a", "name": "A", "item_type": "food"}],
            ))

    def test_missing_natural_key_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="items.yaml",
                # No slug on the second entry.
                entries=[
                    {"slug": "a", "name": "A", "item_type": "food"},
                    {"name": "B", "item_type": "food"},
                ],
            ))

    def test_unsupported_filename_rejected(self) -> None:
        # drops.yaml and skill_tree.yaml aren't a simple list-of-rows so
        # the draft tool refuses them — authors edit those via
        # write_pack_file.
        with override_user(self.parent), self.assertRaises(_VALIDATION_ERRORS):
            cp.draft_pack_entries(DraftPackEntriesIn(
                pack="spring",
                filename="drops.yaml",  # pydantic Literal rejects this
                entries=[{"name": "x"}],
            ))

    def test_reserved_pack_name_blocked(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            cp.draft_pack_entries(DraftPackEntriesIn(
                pack="initial",
                filename="items.yaml",
                entries=[{"slug": "a", "name": "A", "item_type": "food"}],
            ))
