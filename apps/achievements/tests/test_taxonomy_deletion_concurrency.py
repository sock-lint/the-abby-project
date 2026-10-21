"""Real PostgreSQL FK/admission and current-authority delete boundaries."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from unittest import skipUnless
from unittest.mock import patch

from django.db import close_old_connections, connection, connections, transaction, IntegrityError
from django.test import TransactionTestCase, override_settings

from apps.accounts.models import User
from apps.achievements.models import Skill, SkillCategory, SkillProgress
from config.tests.factories import make_family


@skipUnless(connection.vendor == "postgresql", "PostgreSQL row locks required")
@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TaxonomyDeletionConcurrencyTests(TransactionTestCase):
    def setUp(self):
        own = make_family(parents=[{"username": "delete-lock-author", "is_staff": True}])
        other = make_family(children=[{"username": "delete-lock-child"}])
        self.parent, self.child = own.parents[0], other.children[0]
        self.category = SkillCategory.objects.create(name="Deletion lock category")
        self.skill = Skill.objects.create(name="Deletion lock skill", category=self.category)

    def worker(self, function):
        close_old_connections()
        try:
            return function()
        finally:
            connections.close_all()

    def wait_for_lock(self, pid):
        deadline = monotonic() + 8
        while monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute("SELECT wait_event_type FROM pg_stat_activity WHERE pid = %s", [pid])
                row = cursor.fetchone()
            if row and row[0] == "Lock":
                return
            sleep(0.01)
        self.fail("The competing transaction did not wait on the expected row lock.")

    def test_committed_incoming_fk_after_delete_wait_is_preserved(self):
        from apps.rpg.content.taxonomy_deletion import TaxonomyInUse, delete_taxonomy
        inserted, delete_started, release = Event(), Event(), Event()
        pids = []

        def insert():
            with transaction.atomic():
                SkillProgress.objects.create(user=self.child, skill=self.skill, xp_points=321, level=2)
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                inserted.set()
                self.assertTrue(release.wait(10))

        def delete():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids.append(cursor.fetchone()[0])
            delete_started.set()
            with self.assertRaises(TaxonomyInUse):
                delete_taxonomy(self.parent, Skill, self.skill.pk)

        with ThreadPoolExecutor(max_workers=2) as pool:
            writer = pool.submit(self.worker, insert)
            deleter = None
            try:
                self.assertTrue(inserted.wait(8))
                deleter = pool.submit(self.worker, delete)
                self.assertTrue(delete_started.wait(8))
                self.wait_for_lock(pids[0])
            finally:
                release.set()
                writer.result(timeout=12)
                if deleter:
                    deleter.result(timeout=12)
        self.assertEqual(SkillProgress.objects.get(user=self.child, skill=self.skill).xp_points, 321)

    def test_full_target_lock_blocks_new_fk_until_safe_delete_commits(self):
        from apps.rpg.content import taxonomy_deletion as deletion
        locked, writer_started, release = Event(), Event(), Event()
        pids = []
        original = deletion._has_incoming_relation

        def check(obj):
            locked.set()
            self.assertTrue(release.wait(10))
            return original(obj)

        def insert():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids.append(cursor.fetchone()[0])
            writer_started.set()
            with self.assertRaises(IntegrityError), transaction.atomic():
                SkillProgress.objects.create(user=self.child, skill_id=self.skill.pk, xp_points=123)
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")

        with patch.object(deletion, "_has_incoming_relation", side_effect=check), ThreadPoolExecutor(max_workers=2) as pool:
            deleter = pool.submit(self.worker, lambda: deletion.delete_taxonomy(self.parent, Skill, self.skill.pk))
            writer = None
            try:
                self.assertTrue(locked.wait(8))
                writer = pool.submit(self.worker, insert)
                self.assertTrue(writer_started.wait(8))
                self.wait_for_lock(pids[0])
            finally:
                release.set()
                deleter.result(timeout=12)
                if writer:
                    writer.result(timeout=12)
        self.assertFalse(Skill.objects.filter(pk=self.skill.pk).exists())
        self.assertFalse(SkillProgress.objects.filter(skill_id=self.skill.pk).exists())

    def test_family_lock_wait_rechecks_revoked_staff_authority_before_catalog_lock(self):
        from apps.families.models import Family
        from apps.rpg.content.taxonomy_deletion import delete_taxonomy
        from rest_framework.exceptions import PermissionDenied
        started = Event()
        pids = []

        def delete():
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pids.append(cursor.fetchone()[0])
            started.set()
            with self.assertRaises(PermissionDenied):
                delete_taxonomy(self.parent, Skill, self.skill.pk)

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Family.objects.select_for_update().get(pk=self.parent.family_id)
                pending = pool.submit(self.worker, delete)
                self.assertTrue(started.wait(8))
                self.wait_for_lock(pids[0])
                User.objects.filter(pk=self.parent.pk).update(is_staff=False)
            pending.result(timeout=12)
        self.assertTrue(Skill.objects.filter(pk=self.skill.pk).exists())
