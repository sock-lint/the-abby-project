"""Tests for the get_sprite_prompting_playbook MCP tool.

Sanity-pins the playbook so future edits to the constants in
``sprite_prompting_playbook.py`` can't accidentally drop a section
or break the motion-template auto-discovery from
``apps.rpg.sprite_generation.MOTION_TEMPLATES``.
"""
from django.test import TestCase

from apps.accounts.models import User
from apps.rpg.sprite_generation import MOTION_TEMPLATES

from apps.mcp_server.context import set_current_user, reset_current_user
from apps.mcp_server.errors import MCPPermissionDenied
from apps.mcp_server.schemas import GetSpritePromptingPlaybookIn
from apps.mcp_server.tools.sprite_prompting_playbook import (
    get_sprite_prompting_playbook as tool_playbook,
)


class SpritePromptingPlaybookTests(TestCase):
    def setUp(self):
        self.parent = User.objects.create_user(username="pb_parent", password="pw", role="parent")
        self.child = User.objects.create_user(username="pb_kid", password="pw", role="child")

    def _as(self, user):
        return set_current_user(user)

    def test_requires_parent(self):
        tok = self._as(self.child)
        try:
            with self.assertRaises(MCPPermissionDenied):
                tool_playbook(GetSpritePromptingPlaybookIn())
        finally:
            reset_current_user(tok)

    def test_returns_non_empty_playbook(self):
        tok = self._as(self.parent)
        try:
            result = tool_playbook(GetSpritePromptingPlaybookIn())
        finally:
            reset_current_user(tok)
        self.assertIn("playbook", result)
        self.assertIsInstance(result["playbook"], str)
        self.assertGreater(len(result["playbook"]), 500)

    def test_playbook_includes_all_expected_sections(self):
        """Guard against a future edit silently dropping a section."""
        tok = self._as(self.parent)
        try:
            result = tool_playbook(GetSpritePromptingPlaybookIn())
        finally:
            reset_current_user(tok)
        playbook = result["playbook"]
        self.assertIn("# Sprite prompting playbook", playbook)
        self.assertIn("## Failure modes", playbook)
        self.assertIn("## Motion templates", playbook)
        self.assertIn("## Subject specificity rules", playbook)
        self.assertIn("## Reference image rules", playbook)
        self.assertIn("## Tile size and frame count", playbook)

    def test_motion_section_is_sourced_from_motion_templates(self):
        """Adding a new motion in sprite_generation.MOTION_TEMPLATES
        should automatically appear in the playbook so the doc can't
        drift out of sync with the runtime tool."""
        tok = self._as(self.parent)
        try:
            result = tool_playbook(GetSpritePromptingPlaybookIn())
        finally:
            reset_current_user(tok)
        playbook = result["playbook"]
        for slug in MOTION_TEMPLATES:
            self.assertIn(f"`{slug}`", playbook)
        self.assertEqual(set(result["motions"]), set(MOTION_TEMPLATES.keys()))

    def test_failure_mode_count_is_structured(self):
        """Callers should be able to branch on structured fields, not
        just grep the markdown."""
        tok = self._as(self.parent)
        try:
            result = tool_playbook(GetSpritePromptingPlaybookIn())
        finally:
            reset_current_user(tok)
        self.assertIsInstance(result["failure_mode_count"], int)
        self.assertGreaterEqual(result["failure_mode_count"], 5)
