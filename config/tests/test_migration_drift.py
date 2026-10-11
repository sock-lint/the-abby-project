"""Guard the real migration leaf state and metadata-only upgrade contract.

The normal Django test command disables migrations. These checks therefore
run in clean subprocesses against disposable in-memory SQLite databases.
The shared scripts also support the disposable PostgreSQL validation harness.
"""

import os
from pathlib import Path
import subprocess
import sys
import textwrap
import unittest


_REPO_ROOT = Path(__file__).resolve().parents[2]
# Actions' Python needs its loader path to keep the shared runtime aligned.
_BOOTSTRAP_ENV = (
    "PATH", "SystemRoot", "WINDIR", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
    "HOME", "USERPROFILE", "LD_LIBRARY_PATH",
)

_SETUP = """
from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch

import django
django.setup()

from django.apps import apps
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.color import no_style
from django.db import connection
from django.db.migrations.autodetector import MigrationAutodetector
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.recorder import MigrationRecorder
from django.db.migrations.state import ProjectState

assert not getattr(settings, "MIGRATION_MODULES", {}), "syncdb conceals migration drift"

DRIFT_MIGRATIONS = {
    ("accounts", "0009_user_grade_entry_year_help_text"),
    ("rpg", "0023_characterprofile_growth_help_text_and_drop_triggers"),
    ("wellbeing", "0002_dailywellbeingentry_help_text"),
}
HIGH_PK = 2_000_000_000  # High IDs which still fit the preserved integer keys.
DAY = date(2026, 5, 10)
STAMP = datetime(2026, 5, 10, 12, tzinfo=timezone.utc)
GROWTH = [{"pet_id": HIGH_PK, "growth_added": 3, "new_growth": 27, "evolved": False}]
LOOT = {"coins": 17, "items": [{"item_id": HIGH_PK, "quantity": 2}]}
GRATITUDE = ["A preserved gratitude line", "Family time"]


class PreRepairMigrationLoader(MigrationLoader):
    def load_disk(self):
        super().load_disk()
        for key in DRIFT_MIGRATIONS:
            self.disk_migrations.pop(key, None)


def assert_no_drift():
    loader = MigrationLoader(connection)
    changes = MigrationAutodetector(
        loader.project_state(), ProjectState.from_apps(apps),
    ).changes(graph=loader.graph)
    details = {label: [operation.describe() for migration in migrations
                       for operation in migration.operations]
               for label, migrations in changes.items()}
    assert changes == {}, details


def seed_historical_rows(state):
    # Frozen models avoid runtime signals while constructing the old fixture.
    # FK IDs remain valid when late AlterFields re-render related frozen classes.
    registry = state.apps
    User = registry.get_model("accounts", "User")
    Family = registry.get_model("families", "Family")
    Group = registry.get_model("auth", "Group")
    Permission = registry.get_model("auth", "Permission")
    ContentType = registry.get_model("contenttypes", "ContentType")
    family = Family.objects.create(name="Drift Fixture Family", slug="drift-fixture-family")
    password = make_password("preserved-drift-password")
    user = User.objects.create(
        pk=HIGH_PK, username="drift-preserved-user", password=password,
        role="parent", family_id=family.pk, theme="winter", grade_entry_year=2025,
        date_of_birth=date(2010, 4, 3), lorebook_flags={"preserved": [1, "yes"]},
    )
    family.primary_parent_id = user.pk
    family.save(update_fields=["primary_parent"])
    group = Group.objects.create(name="drift-preserved-group")
    content_type = ContentType.objects.create(app_label="accounts", model="drift_fixture")
    permission = Permission.objects.create(
        content_type_id=content_type.pk, name="Drift fixture permission", codename="drift_fixture",
    )
    user.groups.add(group.pk)
    user.user_permissions.add(permission.pk)
    Project = registry.get_model("projects", "Project")
    Project.objects.create(title="Preserved drift project", created_by_id=user.pk, assigned_to_id=user.pk)

    PetSpecies = registry.get_model("pets", "PetSpecies")
    PotionType = registry.get_model("pets", "PotionType")
    UserPet = registry.get_model("pets", "UserPet")
    UserMount = registry.get_model("pets", "UserMount")
    MountExpedition = registry.get_model("pets", "MountExpedition")
    species = PetSpecies.objects.create(slug="drift-species", name="Drift Species", icon="P")
    potion = PotionType.objects.create(slug="drift-potion", name="Drift Potion")
    species.available_potions.add(potion.pk)
    pet = UserPet.objects.create(
        pk=HIGH_PK, user_id=user.pk, species_id=species.pk, potion_id=potion.pk, growth_points=27,
    )
    mount = UserMount.objects.create(user_id=user.pk, species_id=species.pk, potion_id=potion.pk)
    MountExpedition.objects.create(
        pk=HIGH_PK, mount_id=mount.pk, tier="short", status="claimed",
        started_at=STAMP, returns_at=STAMP + timedelta(hours=2),
        claimed_at=STAMP + timedelta(hours=3), loot=LOOT,
    )
    DailyChallenge = registry.get_model("quests", "DailyChallenge")
    DailyChallenge.objects.create(
        pk=HIGH_PK, user_id=user.pk, date=DAY, challenge_type="homework",
        target_value=3, current_progress=2,
    )

    CharacterProfile = registry.get_model("rpg", "CharacterProfile")
    ItemDefinition = registry.get_model("rpg", "ItemDefinition")
    DropTable = registry.get_model("rpg", "DropTable")
    DropLog = registry.get_model("rpg", "DropLog")
    CharacterProfile.objects.create(
        pk=HIGH_PK, user_id=user.pk, level=7, pending_companion_growth=GROWTH,
        unlocks={"old-unlock": {"enabled": True, "enabled_at": "2026-05-01"}},
        consumable_effects_used=["streak_freeze"],
    )
    item = ItemDefinition.objects.create(
        pk=HIGH_PK, slug="drift-item", name="Drift Item", icon="I", item_type="egg",
        pet_species_id=species.pk, metadata={"preserved": {"flags": [True, 3]}},
    )
    for trigger in ("daily_check_in", "journal_entry"):
        DropTable.objects.create(item_id=item.pk, trigger_type=trigger, weight=9)
    DropLog.objects.create(user_id=user.pk, item_id=item.pk, trigger_type="legacy_past_trigger", quantity=2)
    registry.get_model("wellbeing", "DailyWellbeingEntry").objects.create(
        pk=HIGH_PK, user_id=user.pk, date=DAY, affirmation_slug="preserved-affirmation",
        gratitude_lines=GRATITUDE, coin_paid_at=STAMP,
    )
    registry.get_model("homework", "HomeworkDailyCounter").objects.create(
        pk=HIGH_PK, user_id=user.pk, occurred_on=DAY, count=3,
    )
    # Explicit high IDs should represent a valid existing sequence position.
    # SQLite advances automatically; PostgreSQL needs its sequence reset.
    with connection.cursor() as cursor:
        for statement in connection.ops.sequence_reset_sql(no_style(), list(registry.get_models())):
            cursor.execute(statement)
    return {"password": password, "group_id": group.pk, "permission_id": permission.pk,
            "species_id": species.pk, "potion_id": potion.pk, "mount_id": mount.pk}


def assert_preserved_rows(sentinel):
    User = apps.get_model("accounts", "User")
    user = User.objects.get(pk=HIGH_PK)
    assert user.password == sentinel["password"]
    assert user.check_password("preserved-drift-password")
    assert user.theme == "winter" and user.grade_entry_year == 2025
    assert user.date_of_birth == date(2010, 4, 3)
    assert user.lorebook_flags == {"preserved": [1, "yes"]}
    assert user.family.slug == "drift-fixture-family"
    assert user.family.primary_parent_id == user.pk
    assert list(user.groups.values_list("pk", flat=True)) == [sentinel["group_id"]]
    assert list(user.user_permissions.values_list("pk", flat=True)) == [sentinel["permission_id"]]
    project = apps.get_model("projects", "Project").objects.get(title="Preserved drift project")
    assert project.created_by_id == user.pk and project.assigned_to_id == user.pk
    species = apps.get_model("pets", "PetSpecies").objects.get(pk=sentinel["species_id"])
    assert list(species.available_potions.values_list("pk", flat=True)) == [sentinel["potion_id"]]
    pet = apps.get_model("pets", "UserPet").objects.get(pk=HIGH_PK)
    assert (pet.user_id, pet.species_id, pet.potion_id, pet.growth_points) == (
        user.pk, species.pk, sentinel["potion_id"], 27,
    )
    Expedition = apps.get_model("pets", "MountExpedition")
    Challenge = apps.get_model("quests", "DailyChallenge")
    assert Expedition._meta.pk.get_internal_type() == "AutoField"
    assert Challenge._meta.pk.get_internal_type() == "AutoField"
    expedition = Expedition.objects.get(pk=HIGH_PK)
    assert expedition.mount_id == sentinel["mount_id"] and expedition.loot == LOOT
    assert expedition.claimed_at == STAMP + timedelta(hours=3)
    challenge = Challenge.objects.get(pk=HIGH_PK)
    assert (challenge.user_id, challenge.challenge_type, challenge.current_progress) == (user.pk, "homework", 2)
    profile = apps.get_model("rpg", "CharacterProfile").objects.get(pk=HIGH_PK)
    assert profile.user_id == user.pk and profile.pending_companion_growth == GROWTH
    assert profile.unlocks == {"old-unlock": {"enabled": True, "enabled_at": "2026-05-01"}}
    assert profile.consumable_effects_used == ["streak_freeze"]
    item = apps.get_model("rpg", "ItemDefinition").objects.get(pk=HIGH_PK)
    assert item.pet_species_id == species.pk and item.metadata == {"preserved": {"flags": [True, 3]}}
    drops = apps.get_model("rpg", "DropTable").objects.filter(item=item)
    assert set(drops.values_list("trigger_type", flat=True)) == {"daily_check_in", "journal_entry"}
    log = apps.get_model("rpg", "DropLog").objects.get(item=item)
    assert log.user_id == user.pk and log.trigger_type == "legacy_past_trigger" and log.quantity == 2
    wellbeing = apps.get_model("wellbeing", "DailyWellbeingEntry").objects.get(pk=HIGH_PK)
    assert wellbeing.user_id == user.pk and wellbeing.gratitude_lines == GRATITUDE
    assert wellbeing.coin_paid_at == STAMP and wellbeing.affirmation_slug == "preserved-affirmation"
    Counter = apps.get_model("homework", "HomeworkDailyCounter")
    counter = Counter.objects.get(pk=HIGH_PK)
    assert counter.user_id == user.pk and counter.count == 3
    assert Counter._meta.indexes[0].name == "homework_h_user_id_dc01a8_idx"
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, Counter._meta.db_table)
    assert constraints["homework_h_user_id_dc01a8_idx"]["index"]
    return user


def exercise_current_crud(sentinel):
    preserved = assert_preserved_rows(sentinel)
    User = apps.get_model("accounts", "User")
    user = User.objects.create_user(
        username="drift-current-user", password="current-drift-password",
        role="parent", family=preserved.family, grade_entry_year=2026,
        lorebook_flags={"new": [True]},
    )
    assert user.pk > HIGH_PK
    user.refresh_from_db()
    assert user.check_password("current-drift-password") and user.grade_entry_year == 2026
    profile = apps.get_model("rpg", "CharacterProfile").objects.get(user=user)
    assert profile.pk > HIGH_PK  # Created by the real accounts post_save signal.
    profile.pending_companion_growth = [{"pet_id": HIGH_PK, "growth_added": 1}]
    profile.save(update_fields=["pending_companion_growth"])
    profile.refresh_from_db()
    assert profile.pending_companion_growth == [{"pet_id": HIGH_PK, "growth_added": 1}]

    Expedition = apps.get_model("pets", "MountExpedition")
    expedition = Expedition.objects.create(
        mount_id=sentinel["mount_id"], tier="short", returns_at=STAMP, loot={"coins": 1},
    )
    assert expedition.pk > HIGH_PK
    expedition.loot = {"coins": 2}
    expedition.save(update_fields=["loot"])
    expedition.refresh_from_db()
    assert expedition.loot == {"coins": 2}
    Challenge = apps.get_model("quests", "DailyChallenge")
    challenge = Challenge.objects.create(user=user, date=DAY, challenge_type="homework")
    assert challenge.pk > HIGH_PK
    challenge.current_progress = 1
    challenge.save(update_fields=["current_progress"])
    challenge.refresh_from_db()
    assert challenge.current_progress == 1

    DropTable = apps.get_model("rpg", "DropTable")
    for trigger in ("movement_session", "expedition_returned"):
        drop = DropTable.objects.create(item_id=HIGH_PK, trigger_type=trigger)
        drop.full_clean()
        drop.delete()
    Wellbeing = apps.get_model("wellbeing", "DailyWellbeingEntry")
    wellbeing = Wellbeing.objects.create(
        user=user, date=DAY, affirmation_slug="new-affirmation", gratitude_lines=["New line"],
    )
    assert wellbeing.pk > HIGH_PK
    wellbeing.gratitude_lines = ["Updated line"]
    wellbeing.save(update_fields=["gratitude_lines"])
    wellbeing.refresh_from_db()
    assert wellbeing.gratitude_lines == ["Updated line"]
    Counter = apps.get_model("homework", "HomeworkDailyCounter")
    counter = Counter.objects.create(user=user, occurred_on=DAY, count=1)
    assert counter.pk > HIGH_PK
    counter.count = 2
    counter.save(update_fields=["count"])
    counter.refresh_from_db()
    assert counter.count == 2

    for obj in (expedition, challenge, wellbeing, counter, user):
        model, pk = type(obj), obj.pk
        obj.delete()
        assert not model.objects.filter(pk=pk).exists()
    assert_preserved_rows(sentinel)


def database_snapshot():
    with connection.cursor() as cursor:
        tables = sorted(connection.introspection.table_names())
        if connection.vendor == "sqlite":
            cursor.execute("SELECT type, name, tbl_name, sql FROM sqlite_master ORDER BY type, name")
            schema = cursor.fetchall()
            cursor.execute("SELECT name, seq FROM sqlite_sequence WHERE name != 'django_migrations' ORDER BY name")
            sequences = cursor.fetchall()
        elif connection.vendor == "postgresql":
            schema = []
            for query in (
                "SELECT table_name, column_name, data_type, udt_name, is_nullable, column_default, identity_generation FROM information_schema.columns WHERE table_schema = current_schema() ORDER BY table_name, ordinal_position",
                "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema() ORDER BY tablename, indexname",
                "SELECT c.relname, k.conname, pg_get_constraintdef(k.oid) FROM pg_constraint k JOIN pg_class c ON c.oid = k.conrelid JOIN pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = current_schema() ORDER BY c.relname, k.conname",
            ):
                cursor.execute(query)
                schema.append(cursor.fetchall())
            cursor.execute("SELECT sequencename, data_type, start_value, min_value, max_value, increment_by, cycle, cache_size, last_value FROM pg_sequences WHERE schemaname = current_schema() AND sequencename != 'django_migrations_id_seq' ORDER BY sequencename")
            sequences = cursor.fetchall()
        else:
            raise AssertionError("Only disposable SQLite and PostgreSQL fixtures are supported")
        rows = {}
        for table in tables:
            if table == "django_migrations":
                continue
            constraints = connection.introspection.get_constraints(cursor, table)
            primary = next(info["columns"] for info in constraints.values() if info["primary_key"])
            order = ", ".join(connection.ops.quote_name(column) for column in primary)
            cursor.execute("SELECT * FROM " + connection.ops.quote_name(table) + " ORDER BY " + order)
            rows[table] = cursor.fetchall()
    return schema, rows, sequences
"""

_FRESH_CHECK = """
assert_no_drift()
executor = MigrationExecutor(connection)
targets = executor.loader.graph.leaf_nodes()
state = executor.migrate(targets)
sentinel = seed_historical_rows(state)
exercise_current_crud(sentinel)
executor = MigrationExecutor(connection)
executor.loader.check_consistent_history(connection)
assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
assert_no_drift()
"""

_UPGRADE_CHECK = """
with patch("django.db.migrations.executor.MigrationLoader", PreRepairMigrationLoader):
    executor = MigrationExecutor(connection)
    original_state = executor.migrate(executor.loader.graph.leaf_nodes())
sentinel = seed_historical_rows(original_state)
recorded_before = set(MigrationRecorder(connection).applied_migrations())
assert not (recorded_before & DRIFT_MIGRATIONS)
before = database_snapshot()
sql = []
def capture(execute, statement, params, many, context):
    sql.append(statement)
    return execute(statement, params, many, context)
with connection.execute_wrapper(capture):
    executor = MigrationExecutor(connection)
    executor.loader.check_consistent_history(connection)
    targets = executor.loader.graph.leaf_nodes()
    plan = executor.migration_plan(targets)
    assert {(migration.app_label, migration.name) for migration, backwards in plan} == DRIFT_MIGRATIONS
    assert not any(backwards for migration, backwards in plan)
    executor.migrate(targets)
assert database_snapshot() == before
recorded_after = set(MigrationRecorder(connection).applied_migrations())
assert recorded_after - recorded_before == DRIFT_MIGRATIONS
assert recorded_before <= recorded_after
writes = [statement for statement in sql if statement.lstrip().split()[0].upper()
          in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "REPLACE", "TRUNCATE"}]
assert len(writes) == len(DRIFT_MIGRATIONS), writes
assert all(statement.startswith('INSERT INTO "django_migrations"') for statement in writes), writes
assert_no_drift()
exercise_current_crud(sentinel)
executor = MigrationExecutor(connection)
assert executor.migration_plan(executor.loader.graph.leaf_nodes()) == []
"""


class RealMigrationDriftTests(unittest.TestCase):
    def run_migration_check(self, code):
        env = {key: os.environ[key] for key in _BOOTSTRAP_ENV if key in os.environ}
        env.update({
            "DJANGO_SETTINGS_MODULE": "config.settings_test",
            "DATABASE_URL": "sqlite:///:memory:",
            "SECRET_KEY": "migration-drift-disposable-key",
            "DEBUG": "True",
        })
        boundary = "\nassert connection.vendor == 'sqlite'\nassert connection.settings_dict['NAME'] == ':memory:'\n"
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent(_SETUP) + boundary + textwrap.dedent(code)],
            cwd=_REPO_ROOT, env=env, capture_output=True, text=True, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_all_runtime_models_match_real_migration_leaf_state(self):
        self.run_migration_check("assert_no_drift()")

    def test_fresh_real_migrations_support_current_affected_model_crud(self):
        self.run_migration_check(_FRESH_CHECK)

    def test_existing_leaf_upgrade_preserves_schema_rows_and_sequences(self):
        self.run_migration_check(_UPGRADE_CHECK)
