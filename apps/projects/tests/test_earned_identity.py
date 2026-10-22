"""Saved cosmetics follow the existing self/family access boundaries."""
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.achievements.models import Badge, SkillProgress, UserBadge
from apps.projects.models import Project
from apps.rewards.models import CoinLedger
from apps.rpg.models import CharacterProfile, DropLog, ItemDefinition, UserInventory
from config.tests.base import BaseFamilyAPITestCase
from config.tests.factories import make_family


class EarnedIdentityTests(BaseFamilyAPITestCase):
    family_parents = [{"username": "identity-parent"}]
    family_children = [{"username": "identity-child", "display_name": "Rowan"},
                       {"username": "identity-sibling"}]

    def setUp(self):
        self.parent = self.parents[0]
        self.child = self.children[0]
        self.other = make_family("Other identity family", parents=[{"username": "identity-foreign-parent"}],
                                 children=[{"username": "identity-foreign-child"}])
        self.frame = ItemDefinition.objects.create(
            slug="frame-laurel", name="Laurel Frame", item_type="cosmetic_frame", icon="🌿",
            rarity="rare", metadata={"style": "laurel", "color": "#176343"},
        )
        self.title = ItemDefinition.objects.create(
            slug="title-master-crafter", name="Master Crafter", item_type="cosmetic_title", icon="🔨",
            metadata={"title_text": "Master Crafter"},
        )
        self.badge = Badge.objects.create(name="Identity maker", description="Made something worth sharing.",
                                         icon="🔧", criteria_type="first_project", rarity="rare")
        UserBadge.objects.create(user=self.child, badge=self.badge)
        UserInventory.objects.bulk_create([
            UserInventory(user=self.child, item=self.frame), UserInventory(user=self.child, item=self.title),
        ])
        CharacterProfile.objects.filter(user=self.child).update(
            active_frame=self.frame, active_title=self.title, active_trophy_badge=self.badge,
        )
        self.project = Project.objects.create(title="A bird feeder", created_by=self.parent, assigned_to=self.child)
        self.client.force_authenticate(self.child)

    def signature(self, project=None):
        response = self.client.get(f"/api/projects/{(project or self.project).pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("maker_signature", response.data)
        return response.data["maker_signature"]

    def assert_child_identity(self, identity):
        self.assertEqual(identity["id"], self.child.pk)
        self.assertEqual(identity["username"], self.child.username)
        self.assertEqual(identity["display_name"], "Rowan")
        self.assertIsNone(identity["avatar"])
        self.assertEqual(identity["active_frame"]["slug"], self.frame.slug)
        self.assertEqual(identity["active_frame"]["metadata"], self.frame.metadata)
        self.assertEqual(identity["active_title"]["slug"], self.title.slug)
        self.assertEqual(identity["active_trophy_badge"], {
            "id": self.badge.pk, "name": self.badge.name, "icon": self.badge.icon,
            "catalog_icon": None, "rarity": "rare", "description": self.badge.description,
        })
        self.assertEqual(set(identity), {"id", "username", "display_name", "avatar", "active_frame",
                                         "active_title", "active_trophy_badge"})

    @staticmethod
    def earned_state():
        return {model._meta.label: list(model.objects.order_by("pk").values())
                for model in (CharacterProfile, UserInventory, UserBadge, CoinLedger, SkillProgress, DropLog)}

    def test_child_and_family_parent_see_assigned_maker_instead_of_parent_creator(self):
        before = self.earned_state()
        for user in (self.child, self.parent):
            self.client.force_authenticate(user)
            self.assert_child_identity(self.signature())
        self.assertEqual(self.earned_state(), before)

    def test_project_list_keeps_its_existing_compact_contract(self):
        response = self.client.get("/api/projects/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("maker_signature", response.data["results"][0])

    def test_identity_is_self_scoped_on_pulse_and_dashboard(self):
        before = self.earned_state()
        pulse = self.client.get(f"/api/pulse/?user_id={self.other.children[0].pk}")
        self.assertEqual(pulse.status_code, 200)
        self.assertIn("identity", pulse.data)
        self.assert_child_identity(pulse.data["identity"])
        dashboard = self.client.get(f"/api/dashboard/?user_id={self.other.children[0].pk}")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn("identity", dashboard.data["rpg"])
        self.assertEqual(dashboard.data["rpg"]["identity"], pulse.data["identity"])
        self.assertEqual(self.earned_state(), before)
        self.client.force_authenticate(self.parent)
        parent = self.client.get("/api/pulse/").data["identity"]
        self.assertEqual(parent["id"], self.parent.pk)
        self.assertIsNone(parent["active_frame"])
        self.assertIsNone(parent["active_title"])
        self.assertIsNone(parent["active_trophy_badge"])

    def test_unassigned_family_draft_has_no_maker(self):
        self.client.force_authenticate(self.parent)
        draft = Project.objects.create(title="Choose a maker", created_by=self.parent)
        self.assertIsNone(self.signature(draft))

    def test_missing_cosmetics_and_blank_display_name_have_plain_fallbacks(self):
        CharacterProfile.objects.filter(user=self.child).update(active_frame=None, active_title=None,
                                                               active_trophy_badge=None)
        self.child.display_name = ""
        self.child.save(update_fields=["display_name"])
        identity = self.signature()
        self.assertEqual(identity["display_name"], self.child.username)
        for field in ("active_frame", "active_title", "active_trophy_badge"):
            self.assertIsNone(identity[field])

    def test_photo_urls_keep_the_api_origin_for_separate_native_clients(self):
        self.child.avatar = "avatars/synthetic-maker.png"
        self.child.save(update_fields=["avatar"])
        identities = (
            self.signature(),
            self.client.get("/api/pulse/").data["identity"],
            self.client.get("/api/dashboard/").data["rpg"]["identity"],
        )
        for identity in identities:
            self.assertEqual(identity["avatar"], "http://testserver/media/avatars/synthetic-maker.png")

    def test_missing_saved_character_is_not_created_by_pulse_or_project_read(self):
        CharacterProfile.objects.filter(user=self.child).delete()
        self.assertIsNone(self.signature())
        response = self.client.get("/api/pulse/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("identity", response.data)
        self.assertIsNone(response.data["identity"])
        self.assertFalse(CharacterProfile.objects.filter(user=self.child).exists())

    def test_foreign_family_cannot_read_maker_and_legacy_assignment_stays_hidden(self):
        self.client.force_authenticate(self.other.parents[0])
        self.assertEqual(self.client.get(f"/api/projects/{self.project.pk}/").status_code, 404)
        legacy = Project.objects.create(title="Legacy foreign assignment", created_by=self.parent,
                                        assigned_to=self.other.children[0])
        self.client.force_authenticate(self.parent)
        self.assertEqual(self.client.get(f"/api/projects/{legacy.pk}/").status_code, 404)
        self.client.force_authenticate(self.child)
        self.assertEqual(self.client.get(f"/api/projects/{legacy.pk}/").status_code, 404)

    def test_family_assignment_with_foreign_creator_uses_only_assigned_maker(self):
        Project.objects.filter(pk=self.project.pk).update(created_by=self.other.parents[0])
        self.assert_child_identity(self.signature())

    def test_submitted_signature_is_read_only_and_cannot_equip_or_grant(self):
        self.client.force_authenticate(self.parent)
        before = self.earned_state()
        response = self.client.patch(f"/api/projects/{self.project.pk}/", {
            "description": "A new description", "maker_signature": {
                "id": self.other.children[0].pk, "active_frame": None, "active_title": None,
            },
        }, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        self.assert_child_identity(response.data["maker_signature"])
        self.project.refresh_from_db()
        self.assertEqual(self.project.assigned_to_id, self.child.pk)
        self.assertEqual(self.earned_state(), before)

    def test_project_identity_does_not_query_each_cosmetic_separately(self):
        with CaptureQueriesContext(connection) as queries:
            self.assert_child_identity(self.signature())
        cosmetic_queries = [row["sql"] for row in queries.captured_queries
                            if row["sql"].lstrip().upper().startswith("SELECT")
                            and 'FROM "rpg_itemdefinition"' in row["sql"]]
        self.assertEqual(cosmetic_queries, [])
