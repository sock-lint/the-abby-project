"""Ownership, private transport and rollback gates for the live-test fixture."""
import copy
from io import StringIO
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.forms.models import model_to_dict
from django.test import SimpleTestCase, TestCase
from rest_framework.authtoken.models import Token

from apps.families.live_tests import (
    BASE_URL, FAMILY_NAME, FAMILY_SLUG, NAMESPACE, USERNAMES,
    provision_live_test_family, read_private_credentials, validate_credentials,
)
from apps.families.models import Family, LiveTestFamily
from apps.rpg.models import CharacterProfile
from config.tests.factories import make_family


def credentials():
    return {
        "schemaVersion": 1, "baseUrl": BASE_URL, "familySlug": FAMILY_SLUG,
        "parent": {"username": USERNAMES["parent"], "password": "fixture-parent-4K!8xV"},
        "child": {"username": USERNAMES["child"], "password": "fixture-child-9N!2qW"},
    }


def add_expected_ids(payload, receipt):
    result = copy.deepcopy(payload)
    result["familyId"] = receipt["familyId"]
    for role in USERNAMES:
        result[role]["id"] = receipt[role]["id"]
    return result


class PrivateLiveCredentialTests(SimpleTestCase):
    def test_accepts_only_the_exact_reserved_schema(self):
        self.assertEqual(validate_credentials(credentials()), credentials())
        invalid = []
        for key, value in (("schemaVersion", True), ("baseUrl", "https://example.com"),
                           ("familySlug", "default-family"), ("unexpected", "value")):
            payload = credentials()
            payload[key] = value
            invalid.append(payload)
        payload = credentials()
        payload["parent"]["username"] = "someone-real"
        invalid.append(payload)
        payload = credentials()
        payload["parent"]["password"] = "short"
        invalid.append(payload)
        payload = credentials()
        payload["familyId"] = 1
        invalid.append(payload)
        payload = add_expected_ids(credentials(), {"familyId": 1, "parent": {"id": 2}, "child": {"id": 3}})
        payload["child"]["id"] = True
        invalid.append(payload)
        payload = credentials()
        payload["child"]["id"] = 3
        invalid.append(payload)
        for payload in invalid:
            with self.subTest(keys=list(payload)), self.assertRaises(CommandError):
                validate_credentials(payload)

    def test_private_file_requires_absolute_regular_owner_only_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_text(json.dumps(credentials()), encoding="utf-8")
            path.chmod(0o600)
            self.assertEqual(read_private_credentials(str(path)), credentials())
            with self.assertRaises(CommandError):
                read_private_credentials("credentials.json")
            path.chmod(0o640)
            with self.assertRaises(CommandError):
                read_private_credentials(str(path))
            path.chmod(0o600)
            link = Path(directory) / "link"
            link.symlink_to(path)
            with self.assertRaises(CommandError):
                read_private_credentials(str(link))
            linked = Path(directory) / "hardlink"
            os.link(path, linked)
            with self.assertRaises(CommandError):
                read_private_credentials(str(linked))
            linked.unlink()
            with self.assertRaises(CommandError):
                read_private_credentials(directory)
            fifo = Path(directory) / "fifo"
            os.mkfifo(fifo, 0o600)
            with self.assertRaises(CommandError):
                read_private_credentials(str(fifo))

    def test_bad_contents_are_bounded_and_not_echoed(self):
        private_detail = "never-echo-this-private-value"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            for content in ("{\"password\":\"" + private_detail, private_detail * 1000):
                path.write_text(content, encoding="utf-8")
                path.chmod(0o600)
                with self.assertRaises(CommandError) as error:
                    read_private_credentials(str(path))
                self.assertNotIn(private_detail, str(error.exception))


class LiveTestFamilyProvisioningTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.payload = credentials()
        self.real = make_family(
            name="A real family", parents=[{"username": "real-parent"}],
            children=[{"username": "real-child"}],
        )
        self.real_token = Token.objects.create(user=self.real.parents[0])

    def provision(self, **kwargs):
        return provision_live_test_family(self.payload, **kwargs)

    def fixture_users(self, receipt):
        return tuple(self.User.objects.get(pk=receipt[role]["id"]) for role in USERNAMES)

    def test_creates_a_distinct_owned_nonstaff_family_without_tokens(self):
        receipt = self.provision()
        self.assertEqual(receipt["status"], "created")
        family = Family.objects.get(pk=receipt["familyId"])
        parent, child = self.fixture_users(receipt)
        self.assertEqual((family.name, family.slug), (FAMILY_NAME, FAMILY_SLUG))
        self.assertNotEqual(family.pk, self.real.family.pk)
        self.assertEqual(family.primary_parent_id, parent.pk)
        owner = LiveTestFamily.objects.get(namespace=NAMESPACE)
        self.assertEqual((owner.family_id, owner.parent_id, owner.child_id), (family.pk, parent.pk, child.pk))
        self.assertEqual(set(family.members.values_list("pk", flat=True)), {parent.pk, child.pk})
        for role, user in zip(USERNAMES, (parent, child)):
            self.assertEqual(user.family_id, family.pk)
            self.assertEqual(user.role, role)
            self.assertTrue(user.is_active)
            self.assertFalse(user.is_staff or user.is_superuser)
            self.assertEqual(user.hourly_rate, 0)
            self.assertTrue(user.check_password(self.payload[role]["password"]))
            self.assertTrue(CharacterProfile.objects.filter(user=user).exists())
            self.assertFalse(Token.objects.filter(user=user).exists())
        self.assertTrue(child.lorebook_flags)
        self.assertTrue(all(value is True for value in child.lorebook_flags.values()))
        self.assertTrue(all(key.endswith("_seen") for key in child.lorebook_flags))
        self.assertEqual(Token.objects.get(user=self.real.parents[0]).key, self.real_token.key)
        self.real.family.refresh_from_db()
        self.assertEqual(self.real.family.name, "A real family")

    def test_repeated_provision_is_idempotent_with_expected_receipt_ids(self):
        first = self.provision()
        users = self.fixture_users(first)
        hashes = [user.password for user in users]
        counts = (Family.objects.count(), self.User.objects.count(), CharacterProfile.objects.count())
        second = provision_live_test_family(add_expected_ids(self.payload, first))
        self.assertEqual(second, {**first, "status": "verified"})
        self.assertEqual([user.password for user in self.fixture_users(second)], hashes)
        self.assertEqual((Family.objects.count(), self.User.objects.count(), CharacterProfile.objects.count()), counts)

    def test_reserved_family_slug_is_never_adopted(self):
        Family.objects.create(name=FAMILY_NAME, slug=FAMILY_SLUG)
        count = self.User.objects.count()
        with self.assertRaisesMessage(CommandError, "without ownership"):
            self.provision()
        self.assertEqual(self.User.objects.count(), count)
        self.assertFalse(LiveTestFamily.objects.exists())

    def test_reserved_username_in_real_family_is_never_adopted(self):
        for role in USERNAMES:
            with self.subTest(role=role):
                existing = self.User.objects.create_user(
                    username=USERNAMES[role], password="unrelated", family=self.real.family, role=role,
                )
                original_hash = existing.password
                with self.assertRaisesMessage(CommandError, "without ownership"):
                    self.provision()
                existing.refresh_from_db()
                self.assertEqual(existing.password, original_hash)
                self.assertFalse(Family.objects.filter(slug=FAMILY_SLUG).exists())
                existing.delete()

    def test_expected_ids_without_ownership_cannot_create_accounts(self):
        payload = add_expected_ids(self.payload, {"familyId": 1, "parent": {"id": 2}, "child": {"id": 3}})
        with self.assertRaisesMessage(CommandError, "no ownership receipt"):
            provision_live_test_family(payload)
        self.assertFalse(Family.objects.filter(slug=FAMILY_SLUG).exists())

    def test_drifted_account_privileges_and_identity_fail_closed(self):
        receipt = self.provision()
        parent, _ = self.fixture_users(receipt)
        original = {key: getattr(parent, key) for key in (
            "username", "role", "is_staff", "is_superuser", "is_active", "family_id",
        )}
        for key, value in (
            ("username", "changed-owner"), ("role", "child"), ("is_staff", True),
            ("is_superuser", True), ("is_active", False), ("family_id", self.real.family.pk),
        ):
            with self.subTest(field=key):
                self.User.objects.filter(pk=parent.pk).update(**{key: value})
                with self.assertRaises(CommandError):
                    self.provision(rotate_passwords=True)
                parent.refresh_from_db()
                self.assertEqual(getattr(parent, key), value)
                self.User.objects.filter(pk=parent.pk).update(**{key: original[key]})

    def test_extra_member_and_changed_primary_parent_fail_closed(self):
        receipt = self.provision()
        family = Family.objects.get(pk=receipt["familyId"])
        extra = self.User.objects.create_user(username="unexpected-member", family=family, password="pw")
        with self.assertRaisesMessage(CommandError, "no longer matches"):
            self.provision()
        extra.delete()
        family.primary_parent_id = receipt["child"]["id"]
        family.save(update_fields=["primary_parent"])
        with self.assertRaisesMessage(CommandError, "no longer matches"):
            self.provision()
        family.refresh_from_db()
        self.assertEqual(family.primary_parent_id, receipt["child"]["id"])

    def test_wrong_expected_ids_do_not_change_owned_accounts(self):
        receipt = self.provision()
        payload = add_expected_ids(self.payload, receipt)
        payload["parent"]["id"] = self.real.parents[0].pk
        with self.assertRaisesMessage(CommandError, "do not match"):
            provision_live_test_family(payload, rotate_passwords=True)
        self.assertEqual(LiveTestFamily.objects.get().parent_id, receipt["parent"]["id"])

    def test_password_rotation_is_explicit_and_revokes_only_changed_owned_tokens(self):
        receipt = self.provision()
        parent, child = self.fixture_users(receipt)
        parent_token = Token.objects.create(user=parent)
        child_token = Token.objects.create(user=child)
        payload = add_expected_ids(self.payload, receipt)
        payload["parent"]["password"] = "rotated-fixture-parent-3B!9qZ"
        with self.assertRaisesMessage(CommandError, "explicit rotation"):
            provision_live_test_family(payload)
        self.assertTrue(Token.objects.filter(key=parent_token.key).exists())
        changed = provision_live_test_family(payload, rotate_passwords=True)
        self.assertEqual(changed["status"], "updated")
        parent.refresh_from_db()
        self.assertTrue(parent.check_password(payload["parent"]["password"]))
        self.assertFalse(Token.objects.filter(key=parent_token.key).exists())
        self.assertTrue(Token.objects.filter(key=child_token.key).exists())
        self.assertTrue(Token.objects.filter(key=self.real_token.key).exists())

    def test_invalid_discovery_state_rolls_back_password_and_token_rotation(self):
        receipt = self.provision()
        parent, child = self.fixture_users(receipt)
        parent_token = Token.objects.create(user=parent)
        self.User.objects.filter(pk=child.pk).update(lorebook_flags=[])
        payload = copy.deepcopy(self.payload)
        payload["parent"]["password"] = "rotated-fixture-parent-3B!9qZ"
        with self.assertRaisesMessage(CommandError, "discovery state"):
            provision_live_test_family(payload, rotate_passwords=True)
        parent.refresh_from_db()
        self.assertTrue(parent.check_password(self.payload["parent"]["password"]))
        self.assertTrue(Token.objects.filter(key=parent_token.key).exists())

    def test_owned_intro_flags_update_without_changing_progress(self):
        receipt = self.provision()
        _, child = self.fixture_users(receipt)
        child.lorebook_flags = {"custom_seen": True}
        child.save(update_fields=["lorebook_flags"])
        profile = CharacterProfile.objects.get(user=child)
        before = model_to_dict(profile)
        result = self.provision()
        self.assertEqual(result["status"], "updated")
        child.refresh_from_db()
        self.assertTrue(child.lorebook_flags["custom_seen"])
        profile.refresh_from_db()
        self.assertEqual(model_to_dict(profile), before)

    def test_mid_create_collision_rolls_back_all_fixture_rows(self):
        counts = (Family.objects.count(), self.User.objects.count(), CharacterProfile.objects.count())
        with patch("apps.families.live_tests.LiveTestFamily.objects.create", side_effect=IntegrityError("private database detail")):
            with self.assertRaises(CommandError) as error:
                self.provision()
        self.assertNotIn("private database detail", str(error.exception))
        self.assertEqual((Family.objects.count(), self.User.objects.count(), CharacterProfile.objects.count()), counts)
        self.assertFalse(LiveTestFamily.objects.exists())

    def test_command_emits_only_predictable_nonsecret_receipt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.json"
            path.write_text(json.dumps(self.payload), encoding="utf-8")
            path.chmod(0o600)
            output = StringIO()
            call_command("provision_live_test_family", credentials_file=str(path), stdout=output)
        receipt = json.loads(output.getvalue())
        self.assertEqual(set(receipt), {"schemaVersion", "status", "baseUrl", "familySlug", "familyId", "parent", "child"})
        for role in USERNAMES:
            self.assertEqual(set(receipt[role]), {"id", "username", "role"})
            self.assertNotIn(self.payload[role]["password"], output.getvalue())
