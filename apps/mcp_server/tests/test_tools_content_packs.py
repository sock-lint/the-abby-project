"""Tests for content-pack MCP tools.

Covers the full LLM authoring loop: write YAML -> validate (dry-run) ->
load -> re-load (idempotent) -> list catalog. Also verifies safety rails
(path traversal, reserved names, oversize payloads) and parent-only gating.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.test import TestCase, override_settings
from pydantic import ValidationError as PydanticValidationError

from apps.achievements.models import Badge
from apps.mcp_server.context import override_user
from apps.mcp_server.errors import (
    MCPNotFoundError,
    MCPPermissionDenied,
    MCPValidationError,
)


_VALIDATION_ERRORS = (MCPValidationError, PydanticValidationError)
from apps.mcp_server.schemas import (
    DeleteContentPackIn,
    DeletePackFileIn,
    GetContentPackIn,
    ListContentPacksIn,
    ListRpgCatalogIn,
    LoadContentPackIn,
    PrunePackContentIn,
    ReadPackFileIn,
    ValidateContentPackIn,
    WritePackFileIn,
)
from apps.mcp_server.tools import content_packs as cp
from apps.projects.models import User
from apps.rpg.models import ItemDefinition


# ---------------------------------------------------------------------------
# Isolated packs root per test
# ---------------------------------------------------------------------------


def _isolated_packs_root(tmp: Path) -> Path:
    """Create a throwaway content/rpg/packs/ root for a test."""
    root = tmp / "content" / "rpg" / "packs"
    root.mkdir(parents=True, exist_ok=True)
    return root


class _PacksMixin(TestCase):
    """Redirect BASE_DIR to a tmp dir so each test has its own packs root."""

    def setUp(self) -> None:
        super().setUp()
        self.parent = User.objects.create_user(
            username="p", password="pw", role="parent",
        )
        self.child = User.objects.create_user(
            username="c", password="pw", role="child",
        )
        self.tmp = Path(self._get_tmp_dir())
        self._override = override_settings(BASE_DIR=str(self.tmp))
        self._override.enable()
        _isolated_packs_root(self.tmp)

    def tearDown(self) -> None:
        self._override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)
        super().tearDown()

    def _get_tmp_dir(self) -> str:
        import tempfile
        return tempfile.mkdtemp(prefix="mcp_packs_test_")


# ---------------------------------------------------------------------------
# File CRUD + safety rails
# ---------------------------------------------------------------------------


class WritePackFileTests(_PacksMixin):
    def test_write_creates_pack_dir_and_file(self) -> None:
        with override_user(self.parent):
            result = cp.write_pack_file(WritePackFileIn(
                pack="spring-2026",
                filename="items.yaml",
                yaml_content="items:\n  - slug: test-food\n    name: Test\n    item_type: food\n",
            ))
        self.assertEqual(result["pack"], "spring-2026")
        self.assertTrue(result["bytes_written"] > 0)
        path = self.tmp / "content" / "rpg" / "packs" / "spring-2026" / "items.yaml"
        self.assertTrue(path.exists())

    def test_child_cannot_write(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            cp.write_pack_file(WritePackFileIn(
                pack="spring-2026",
                filename="items.yaml",
                yaml_content="items: []\n",
            ))

    def test_invalid_yaml_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            cp.write_pack_file(WritePackFileIn(
                pack="spring-2026",
                filename="items.yaml",
                yaml_content="items:\n  - : :\n    - broken\n",
            ))

    def test_non_mapping_top_level_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            cp.write_pack_file(WritePackFileIn(
                pack="spring-2026",
                filename="items.yaml",
                yaml_content="- just a list\n- of strings\n",
            ))

    def test_reserved_pack_name_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            cp.write_pack_file(WritePackFileIn(
                pack="initial",
                filename="items.yaml",
                yaml_content="items: []\n",
            ))

    def test_bad_pack_name_regex(self) -> None:
        # Uppercase, dots, underscores-leading, too long — all rejected.
        # 41-char names are caught by Pydantic; the rest by the tool's regex.
        bad = ["Spring", ".hidden", "_bootleg", "a" * 41, "has/slash", "has..dot"]
        for name in bad:
            with self.subTest(name=name):
                with override_user(self.parent), self.assertRaises(
                    _VALIDATION_ERRORS,
                ):
                    cp.write_pack_file(WritePackFileIn(
                        pack=name,
                        filename="items.yaml",
                        yaml_content="items: []\n",
                    ))

    def test_path_traversal_pack_name_rejected(self) -> None:
        # The regex already refuses "../" — confirm the validator fires first.
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            cp.write_pack_file(WritePackFileIn(
                pack="..",
                filename="items.yaml",
                yaml_content="items: []\n",
            ))

    def test_oversize_payload_rejected(self) -> None:
        # Pydantic's max_length catches strings over 200 KB at schema
        # validation time; the tool's byte check is defence-in-depth.
        blob = "# " + ("x" * 200_001)
        with override_user(self.parent), self.assertRaises(_VALIDATION_ERRORS):
            cp.write_pack_file(WritePackFileIn(
                pack="big",
                filename="items.yaml",
                yaml_content=blob,
            ))


class ReadAndDeletePackFileTests(_PacksMixin):
    def test_read_after_write_round_trip(self) -> None:
        content = "items:\n  - slug: a\n    name: A\n    item_type: food\n"
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack="pack-a", filename="items.yaml", yaml_content=content,
            ))
            result = cp.read_pack_file(ReadPackFileIn(
                pack="pack-a", filename="items.yaml",
            ))
        self.assertEqual(result["yaml_content"], content)

    def test_read_missing_file(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            cp.read_pack_file(ReadPackFileIn(
                pack="nonexistent", filename="items.yaml",
            ))

    def test_delete_pack_file(self) -> None:
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack="pack-b", filename="items.yaml", yaml_content="items: []\n",
            ))
            result = cp.delete_pack_file(DeletePackFileIn(
                pack="pack-b", filename="items.yaml",
            ))
        self.assertTrue(result["deleted"])
        path = self.tmp / "content" / "rpg" / "packs" / "pack-b" / "items.yaml"
        self.assertFalse(path.exists())


class ListAndGetPackTests(_PacksMixin):
    def test_list_empty(self) -> None:
        with override_user(self.parent):
            result = cp.list_content_packs(ListContentPacksIn())
        self.assertEqual(result["count"], 0)

    def test_list_after_writes(self) -> None:
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack="one", filename="items.yaml", yaml_content="items: []\n",
            ))
            cp.write_pack_file(WritePackFileIn(
                pack="two", filename="quests.yaml", yaml_content="quests: []\n",
            ))
            result = cp.list_content_packs(ListContentPacksIn())
        self.assertEqual(result["count"], 2)
        names = {p["name"] for p in result["packs"]}
        self.assertEqual(names, {"one", "two"})
        # Each pack reports its namespace prefix.
        for p in result["packs"]:
            self.assertEqual(p["namespace_prefix"], f"{p['name']}-")

    def test_get_nonexistent(self) -> None:
        with override_user(self.parent), self.assertRaises(MCPNotFoundError):
            cp.get_content_pack(GetContentPackIn(pack="ghost"))


class DeleteContentPackTests(_PacksMixin):
    def test_delete_requires_confirm(self) -> None:
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack="dp", filename="items.yaml", yaml_content="items: []\n",
            ))
            with self.assertRaises(MCPValidationError):
                cp.delete_content_pack(DeleteContentPackIn(pack="dp"))
            result = cp.delete_content_pack(
                DeleteContentPackIn(pack="dp", confirm=True),
            )
        self.assertTrue(result["deleted"])

    def test_delete_refuses_unexpected_files(self) -> None:
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack="dp2", filename="items.yaml", yaml_content="items: []\n",
            ))
        # Sneak an extra file into the pack dir.
        stray = self.tmp / "content" / "rpg" / "packs" / "dp2" / "stray.txt"
        stray.write_text("hi", encoding="utf-8")
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            cp.delete_content_pack(
                DeleteContentPackIn(pack="dp2", confirm=True),
            )


# ---------------------------------------------------------------------------
# Validate + load
# ---------------------------------------------------------------------------


class ValidateAndLoadTests(_PacksMixin):
    def _seed_badge(self) -> Badge:
        return Badge.objects.create(
            name="Test Badge",
            description="",
            criteria_type="first_clock_in",
            rarity="common",
        )

    def _write_simple_items(self, pack: str) -> None:
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack=pack,
                filename="items.yaml",
                yaml_content=(
                    "items:\n"
                    "  - slug: biscuit\n"
                    "    name: Biscuit\n"
                    "    item_type: food\n"
                    "    rarity: common\n"
                    "    coin_value: 1\n"
                ),
            ))

    def test_validate_empty_pack_rejected(self) -> None:
        # create an empty pack dir — no YAML files
        (self.tmp / "content" / "rpg" / "packs" / "emptypack").mkdir()
        with override_user(self.parent), self.assertRaises(MCPValidationError):
            cp.validate_content_pack(ValidateContentPackIn(pack="emptypack"))

    def test_validate_dry_run_does_not_persist(self) -> None:
        self._write_simple_items("dryrun")
        with override_user(self.parent):
            result = cp.validate_content_pack(
                ValidateContentPackIn(pack="dryrun"),
            )
        self.assertTrue(result["dry_run"])
        # Even though the loader says "created food_item", nothing actually persisted.
        self.assertFalse(
            ItemDefinition.objects.filter(slug="dryrun-biscuit").exists(),
        )

    def test_load_persists_and_is_idempotent(self) -> None:
        self._write_simple_items("spring")
        with override_user(self.parent):
            first = cp.load_content_pack(LoadContentPackIn(pack="spring"))
            second = cp.load_content_pack(LoadContentPackIn(pack="spring"))
            summary = cp.get_content_pack(GetContentPackIn(pack="spring"))
        # Namespaced slug landed.
        self.assertTrue(
            ItemDefinition.objects.filter(slug="spring-biscuit").exists(),
        )
        # First run creates, second run updates (idempotent upsert).
        self.assertEqual(first["created"].get("item_food", 0), 1)
        self.assertEqual(second["created"].get("item_food", 0), 0)
        self.assertEqual(second["updated"].get("item_food", 0), 1)
        # Manifest recorded.
        self.assertIsNotNone(summary["last_loaded_at"])
        self.assertIn("item_food", summary["last_load_stats"]["updated"])

    def test_load_with_dry_run_does_not_write_manifest(self) -> None:
        self._write_simple_items("drypack")
        with override_user(self.parent):
            cp.load_content_pack(LoadContentPackIn(pack="drypack", dry_run=True))
            summary = cp.get_content_pack(GetContentPackIn(pack="drypack"))
        self.assertIsNone(summary["last_loaded_at"])

    def test_load_surfaces_reference_errors_as_validation(self) -> None:
        # quests.yaml referencing a badge that doesn't exist → loader raises
        # ContentPackError → tool converts to MCPValidationError.
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack="badref",
                filename="quests.yaml",
                yaml_content=(
                    "quests:\n"
                    "  - name: Ghost Quest\n"
                    "    quest_type: boss\n"
                    "    target_value: 100\n"
                    "    required_badge: Does Not Exist\n"
                ),
            ))
            with self.assertRaises(MCPValidationError):
                cp.validate_content_pack(
                    ValidateContentPackIn(pack="badref"),
                )

    def test_child_cannot_load(self) -> None:
        self._write_simple_items("nope")
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            cp.load_content_pack(LoadContentPackIn(pack="nope"))


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class ListRpgCatalogTests(_PacksMixin):
    def test_empty_catalog(self) -> None:
        with override_user(self.parent):
            result = cp.list_rpg_catalog(ListRpgCatalogIn())
        self.assertEqual(result["counts"]["items"], 0)
        self.assertEqual(result["counts"]["badges"], 0)

    def test_catalog_after_load(self) -> None:
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack="catpack",
                filename="items.yaml",
                yaml_content=(
                    "items:\n"
                    "  - slug: apple\n"
                    "    name: Apple\n"
                    "    item_type: food\n"
                    "  - slug: title-pro\n"
                    "    name: Pro\n"
                    "    item_type: cosmetic_title\n"
                ),
            ))
            cp.load_content_pack(LoadContentPackIn(pack="catpack"))
            result = cp.list_rpg_catalog(ListRpgCatalogIn())
        slugs = {it["slug"] for it in result["items"]}
        self.assertIn("catpack-apple", slugs)
        self.assertIn("catpack-title-pro", slugs)

    def test_catalog_item_type_filter(self) -> None:
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack="filt",
                filename="items.yaml",
                yaml_content=(
                    "items:\n"
                    "  - slug: f\n"
                    "    name: F\n"
                    "    item_type: food\n"
                    "  - slug: t\n"
                    "    name: T\n"
                    "    item_type: cosmetic_title\n"
                ),
            ))
            cp.load_content_pack(LoadContentPackIn(pack="filt"))
            foods = cp.list_rpg_catalog(ListRpgCatalogIn(item_type="food"))
        self.assertEqual(len(foods["items"]), 1)
        self.assertEqual(foods["items"][0]["slug"], "filt-f")

    def test_child_cannot_read_catalog(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            cp.list_rpg_catalog(ListRpgCatalogIn())


class PrunePackContentMCPTests(_PacksMixin):
    """Thin MCP wrapper around the prune_pack helper.

    Permissions + pack-name validation are the new surface here; the
    deletion logic itself is covered in apps/rpg/tests/test_prune_pack_content.py.
    """

    def _seed_pack_with_drops_and_rewards(self, pack: str) -> None:
        """Write + load a small pack that actually creates a drop + reward."""
        with override_user(self.parent):
            cp.write_pack_file(WritePackFileIn(
                pack=pack, filename="items.yaml",
                yaml_content=(
                    "items:\n"
                    "  - slug: food-a\n"
                    "    name: Food A\n"
                    "    item_type: food\n"
                    "    rarity: common\n"
                    "    coin_value: 1\n"
                ),
            ))
            cp.write_pack_file(WritePackFileIn(
                pack=pack, filename="drops.yaml",
                yaml_content=(
                    "rules:\n"
                    "  - trigger: chore_complete\n"
                    "    item_slugs: [food-a]\n"
                    "    weight: 2\n"
                ),
            ))
            cp.write_pack_file(WritePackFileIn(
                pack=pack, filename="rewards.yaml",
                yaml_content=(
                    "rewards:\n"
                    "  - name: Prune Test Reward\n"
                    "    description: x\n"
                    "    cost_coins: 10\n"
                    "    rarity: common\n"
                    "    fulfillment_kind: digital_item\n"
                    "    item_definition: food-a\n"
                ),
            ))
            cp.load_content_pack(LoadContentPackIn(pack=pack))

    def test_prune_removes_drops_and_rewards(self) -> None:
        from apps.rewards.models import Reward
        from apps.rpg.models import DropTable

        pack = "prunable"
        self._seed_pack_with_drops_and_rewards(pack)
        self.assertTrue(
            DropTable.objects.filter(item__slug=f"{pack}-food-a").exists()
        )
        self.assertTrue(
            Reward.objects.filter(item_definition__slug=f"{pack}-food-a").exists()
        )

        with override_user(self.parent):
            r = cp.prune_pack_content(PrunePackContentIn(pack=pack))
        self.assertEqual(r["drops_deleted"], 1)
        self.assertEqual(r["rewards_deleted"], 1)
        self.assertFalse(r["dry_run"])

        # Rows gone, pack ItemDefinition preserved.
        self.assertFalse(
            DropTable.objects.filter(item__slug=f"{pack}-food-a").exists()
        )
        self.assertFalse(
            Reward.objects.filter(item_definition__slug=f"{pack}-food-a").exists()
        )
        self.assertTrue(
            ItemDefinition.objects.filter(slug=f"{pack}-food-a").exists()
        )

    def test_dry_run_reports_but_persists_nothing(self) -> None:
        from apps.rewards.models import Reward
        from apps.rpg.models import DropTable

        pack = "prunedry"
        self._seed_pack_with_drops_and_rewards(pack)

        with override_user(self.parent):
            r = cp.prune_pack_content(
                PrunePackContentIn(pack=pack, dry_run=True),
            )
        self.assertEqual(r["drops_deleted"], 1)
        self.assertEqual(r["rewards_deleted"], 1)
        self.assertTrue(r["dry_run"])
        # Nothing actually removed.
        self.assertTrue(
            DropTable.objects.filter(item__slug=f"{pack}-food-a").exists()
        )
        self.assertTrue(
            Reward.objects.filter(item_definition__slug=f"{pack}-food-a").exists()
        )

    def test_child_cannot_prune(self) -> None:
        with override_user(self.child), self.assertRaises(MCPPermissionDenied):
            cp.prune_pack_content(PrunePackContentIn(pack="whatever"))

    def test_reserved_pack_name_rejected(self) -> None:
        with override_user(self.parent), self.assertRaises(_VALIDATION_ERRORS):
            cp.prune_pack_content(PrunePackContentIn(pack="initial"))
