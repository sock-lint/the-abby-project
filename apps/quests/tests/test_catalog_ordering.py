"""Same-name challenge definitions retain a deterministic catalog order."""
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.quests.models import QuestDefinition
from config.tests.factories import make_family


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class QuestCatalogOrderingTests(APITestCase):
    def test_same_type_and_name_use_identity_order_after_out_of_order_insertion(self):
        parent = make_family("Catalog order", parents=[{"username": "catalog-order-parent"}]).parents[0]
        self.client.force_authenticate(parent)
        # PostgreSQL may preserve this physical insertion order for tied sort
        # keys. A custom same-name row must not displace the earlier ID.
        QuestDefinition.objects.create(
            id=93, name="Feather Collector", quest_type="collection", target_value=3, is_system=False,
        )
        QuestDefinition.objects.create(
            id=91, name="Feather Collector", quest_type="collection", target_value=3, is_system=True,
        )
        QuestDefinition.objects.create(id=97, name="Zulu boss", quest_type="boss", target_value=3)
        QuestDefinition.objects.create(id=95, name="Alpha collection", quest_type="collection", target_value=3)

        response = self.client.get("/api/quests/catalog/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data], [97, 95, 91, 93])
        self.assertEqual({row["id"]: row["catalog_icon"] for row in response.data if row["id"] in {91, 93}}, {
            91: "challenge-feather-collector", 93: None,
        })
