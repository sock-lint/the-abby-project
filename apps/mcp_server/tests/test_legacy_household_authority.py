"""Legacy RPG tools recheck the authenticated principal before using household data."""
from unittest.mock import patch
from uuid import uuid4

from asgiref.sync import async_to_sync
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.chronicle.models import ChronicleEntry
from apps.mcp_server.auth import _resolve_access
from apps.mcp_server.context import override_user
from apps.mcp_server.server import mcp
from apps.mcp_server.tools import chronicle, inventory, pets
from apps.pets.models import PetSpecies, PotionType, UserPet
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, ItemDefinition, UserInventory
from config.tests.factories import make_family, make_oauth_token


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   MCP_RESOURCE_URL="http://synthetic.invalid/mcp")
class LegacyHouseholdAuthorityTests(TestCase):
    def setUp(self):
        home = make_family("Legacy tools", parents=[{"username": "legacy-parent", "is_staff": True}],
                           children=[{"username": "legacy-child"}])
        self.parent, self.child = home.parents[0], home.children[0]
        other = make_family("Other legacy tools", children=[{"username": "legacy-foreign"}])
        self.other_family, self.foreign = other.family, other.children[0]
        token, _ = make_oauth_token(self.parent, scope="mcp:read mcp:write")
        self.actor, self.scopes = _resolve_access(token.token)
        self.item = ItemDefinition.objects.create(
            slug="authority-growth-tonic", name="Growth Tonic", item_type="consumable",
            metadata={"effect": "growth_tonic", "feeds": 3},
        )
        for target in (self.child, self.foreign):
            UserInventory.objects.create(user=target, item=self.item, quantity=2)
            CharacterProfile.objects.get_or_create(user=target)
        species = PetSpecies.objects.create(slug="authority-pet", name="Saved companion")
        potion = PotionType.objects.create(slug="base", name="Base")
        self.pet = UserPet.objects.create(user=self.child, species=species, potion=potion, is_active=False)
        self.shared = self.entry(self.child, "journal", "Shared reflection", private=False)
        self.private = self.entry(self.child, "grade", "Private reflection", private=True)
        self.daily = self.entry(self.child, "daily_note", "Author-only note")
        self.manual = self.entry(self.child, "manual", "Manual memory")
        self.own = self.entry(self.parent, "journal", "Parent's own journal", private=True)

    def entry(self, user, kind, title, *, private=False):
        today = timezone.localdate()
        return ChronicleEntry.objects.create(
            user=user, kind=kind, title=title, summary=f"Prose for {title}", is_private=private,
            occurred_on=today, chapter_year=today.year if today.month >= 8 else today.year - 1,
        )

    def wire(self, name, params=None, *, actor=None, scopes=None, confirmation=True):
        with override_user(actor or self.actor, scopes=self.scopes if scopes is None else scopes):
            result = async_to_sync(mcp.call_tool)(name, {"params": params or {}, "confirmation": confirmation})
        return result[1] if isinstance(result, tuple) else result.structuredContent

    def assert_error(self, result, code):
        self.assertIn("error", result, result)
        self.assertEqual(result["error"]["code"], code, result)

    def state(self):
        return (UserInventory.objects.get(user=self.child, item=self.item).quantity,
                CharacterProfile.objects.get(user=self.child).pet_growth_boost_remaining,
                UserPet.objects.get(pk=self.pet.pk).is_active)

    def target_calls(self):
        target = {"user_id": self.child.pk}
        return [
            ("list_inventory", target), ("use_consumable", {**target, "item_id": self.item.pk}),
            ("list_cosmetics", target), ("equip_cosmetic", {**target, "item_id": self.item.pk}),
            ("unequip_cosmetic", {**target, "slot": "active_frame"}),
            ("set_trophy_badge", {**target, "badge_id": None}),
            ("list_pets", target), ("list_mounts", target), ("get_pet_stable", target),
            ("get_pet_incubation", target),
            ("start_pet_incubation", {**target, "egg_item_id": self.item.pk, "potion_item_id": self.item.pk,
                                      "request_id": str(uuid4())}),
            ("claim_pet_incubation", {**target, "incubation_id": 999999}),
            ("feed_pet", {**target, "pet_id": self.pet.pk, "food_item_id": self.item.pk}),
            ("activate_pet", {**target, "pet_id": self.pet.pk}),
            ("activate_mount", {**target, "mount_id": 999999}),
            ("list_chronicle_entries", target), ("get_chronicle_summary", target),
        ]

    def test_each_target_tool_rechecks_actor_after_authentication(self):
        for changes in ({"family": self.other_family}, {"role": "child"},
                        {"is_staff": False}, {"is_active": False}):
            get_user_model().objects.filter(pk=self.parent.pk).update(**changes)
            try:
                for name, params in self.target_calls():
                    with self.subTest(changes=changes, tool=name):
                        self.assert_error(self.wire(name, params), "permission_denied")
            finally:
                get_user_model().objects.filter(pk=self.parent.pk).update(
                    family_id=self.parent.family_id, role="parent", is_staff=True, is_active=True,
                )

    def test_entry_and_self_tools_recheck_actor_before_read_or_write(self):
        get_user_model().objects.filter(pk=self.parent.pk).update(family=self.other_family)
        calls = [
            ("mark_chronicle_viewed", {"entry_id": self.shared.pk}),
            ("get_pending_celebration", {}), ("get_today_journal", {}),
            ("write_journal", {"title": "New reflection"}),
            ("update_journal", {"entry_id": self.own.pk, "title": "Changed"}),
            ("create_manual_entry", {"user_id": self.child.pk, "title": "New memory",
                                     "occurred_on": timezone.localdate().isoformat()}),
            ("update_manual_entry", {"entry_id": self.manual.pk, "title": "Changed"}),
            ("delete_chronicle_entry", {"entry_id": self.manual.pk}),
        ]
        for name, params in calls:
            with self.subTest(tool=name):
                self.assert_error(self.wire(name, params), "permission_denied")

    def test_target_departure_after_resolution_cannot_consume_or_activate(self):
        for module, name, params in (
            (inventory, "use_consumable", {"item_id": self.item.pk}),
            (pets, "activate_pet", {"pet_id": self.pet.pk}),
        ):
            original = module.resolve_target_user

            def depart(actor, requested_id):
                target = original(actor, requested_id)
                get_user_model().objects.filter(pk=target.pk).update(family=self.other_family)
                return target

            with self.subTest(tool=name), patch.object(module, "resolve_target_user", side_effect=depart):
                self.assert_error(self.wire(name, {"user_id": self.child.pk, **params}), "not_found")
            self.assertEqual(self.state(), (2, 0, False))
            get_user_model().objects.filter(pk=self.child.pk).update(family_id=self.parent.family_id)
        self.assertEqual(UserInventory.objects.get(user=self.foreign, item=self.item).quantity, 2)
        self.assertFalse(CoinLedger.objects.exists())

    def test_inactive_child_history_preserves_privacy_and_writes_are_denied(self):
        get_user_model().objects.filter(pk=self.child.pk).update(is_active=False)
        visible = self.wire("list_chronicle_entries", {"user_id": self.child.pk})["entries"]
        self.assertEqual({entry["id"] for entry in visible}, {self.shared.pk, self.manual.pk})
        self.assertEqual(len(self.wire("list_inventory", {"user_id": self.child.pk})["inventory"]), 1)
        self.assertEqual(len(self.wire("list_pets", {"user_id": self.child.pk})["pets"]), 1)
        self.assert_error(self.wire("use_consumable", {"user_id": self.child.pk, "item_id": self.item.pk}), "not_found")
        self.assertEqual(self.state(), (2, 0, False))

    def test_current_parent_self_child_self_and_scope_controls(self):
        self.assertEqual(self.wire("get_today_journal")["entry"]["id"], self.own.pk)
        child_entries = self.wire("list_chronicle_entries", actor=self.child)["entries"]
        self.assertEqual({entry["id"] for entry in child_entries},
                         {self.shared.pk, self.private.pk, self.daily.pk, self.manual.pk})
        self.assert_error(self.wire("list_inventory", {"user_id": self.foreign.pk}), "not_found")
        params = {"user_id": self.child.pk, "item_id": self.item.pk}
        self.assert_error(self.wire("use_consumable", params, scopes=frozenset({"mcp:read"})), "permission_denied")
        self.assert_error(self.wire("use_consumable", params, confirmation=False), "confirmation_required")
        self.assertEqual(self.wire("use_consumable", params)["quantity_used"], 1)
        self.assertEqual(self.state(), (1, 3, False))
        self.assertFalse(CoinLedger.objects.exists())

    def test_parent_self_and_child_self_inventory_actions_remain_supported(self):
        UserInventory.objects.create(user=self.parent, item=self.item, quantity=1)
        CharacterProfile.objects.get_or_create(user=self.parent)
        self.assertEqual(self.wire("use_consumable", {"item_id": self.item.pk})["quantity_used"], 1)
        self.assertEqual(self.wire("use_consumable", {"item_id": self.item.pk}, actor=self.child)["quantity_used"], 1)
        self.assertEqual(self.state(), (1, 3, False))
        self.assertEqual(CharacterProfile.objects.get(user=self.parent).pet_growth_boost_remaining, 3)

    def test_entry_owner_departure_after_identity_lookup_cannot_mark_edit_or_delete(self):
        original = chronicle.resolve_target_user

        def depart(actor, requested_id):
            target = original(actor, requested_id)
            get_user_model().objects.filter(pk=target.pk).update(family=self.other_family)
            return target

        for name, params in (
            ("mark_chronicle_viewed", {"entry_id": self.manual.pk}),
            ("update_manual_entry", {"entry_id": self.manual.pk, "title": "Changed"}),
            ("delete_chronicle_entry", {"entry_id": self.manual.pk}),
        ):
            with self.subTest(tool=name), patch.object(chronicle, "resolve_target_user", side_effect=depart):
                self.assert_error(self.wire(name, params), "not_found")
            self.manual.refresh_from_db()
            self.assertEqual(self.manual.title, "Manual memory")
            self.assertIsNone(self.manual.viewed_at)
            get_user_model().objects.filter(pk=self.child.pk).update(family_id=self.parent.family_id)

    def test_private_and_system_entry_identity_controls_are_preserved(self):
        self.assert_error(self.wire("mark_chronicle_viewed", {"entry_id": self.private.pk}), "not_found")
        for name in ("update_manual_entry", "delete_chronicle_entry"):
            self.assert_error(self.wire(name, {"entry_id": self.shared.pk}), "permission_denied")
        self.assertTrue(ChronicleEntry.objects.filter(pk=self.shared.pk).exists())
