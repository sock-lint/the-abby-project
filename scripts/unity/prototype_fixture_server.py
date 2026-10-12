#!/usr/bin/env python
"""Run real Django APIs against disposable, local-only Unity smoke fixtures.

    python scripts/unity/prototype_fixture_server.py --port 0 --ready-file ready.json
    python scripts/unity/prototype_fixture_server.py --check

Requires the project's Python dependencies. The script does not load .env or
open the project's database. Ctrl+C removes the temporary database and media.
All printed credentials belong only to this throwaway test server.

Browser QA can use --fail-first-expedition-start-after-commit and
--fail-first-expedition-claim-after-commit (also --fail-first-start-after-commit
and --fail-first-claim-after-commit). POST /__fixture/finish-expedition/<id>/
advances only an active expedition belonging to a designated fixture mount;
its locked loot and reward state remain intact. POST /__fixture/hold-next-care/
holds the next committed creature/expedition acknowledgement for at most 15s;
observe /__fixture/play-state/, change accounts, then POST /__fixture/release-care/.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
from socketserver import ThreadingMixIn
import sys
from tempfile import TemporaryDirectory
from threading import Event, Lock, Thread
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from wsgiref.simple_server import make_server, WSGIServer


USERNAME = "camp-smoke"
PASSWORD = "only-local-smoke"
PARENT_USERNAME = "camp-parent"
SECOND_USERNAME = "camp-other"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CARE_ACTIVITY: dict[int, dict[str, int]] = {}
EXPEDITION_FIXTURE_MOUNT_IDS: set[int] = set()


class DisposableFixtureServer(ThreadingMixIn, WSGIServer):
    """Serve account replacement while one acknowledgement is held back."""

    daemon_threads = False
    block_on_close = True

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            # Fixture snapshots also query models outside Django's request
            # handler. Release each thread's SQLite handle before temp cleanup.
            from django.db import connections

            connections.close_all()


def configure_django(temporary_root: Path) -> None:
    """Configure isolation before importing models, middleware, or settings."""
    sys.path.insert(0, str(REPOSITORY_ROOT))
    from django.conf import settings

    if settings.configured:
        raise RuntimeError("Run the fixture harness in a fresh Python process.")

    prefixes = (
        "AWS_", "GOOGLE_", "VAPID_", "SENTRY_", "PRINT_", "ANTHROPIC_",
        "GEMINI_", "OLLAMA_", "OPENAI_", "CELERY_", "REDIS_", "EMAIL_",
    )
    for name in list(os.environ):
        if name.startswith(prefixes) or name.endswith(("_API_KEY", "_SECRET", "_TOKEN")):
            os.environ.pop(name, None)
    os.environ.update({
        "DJANGO_SETTINGS_MODULE": "config.settings_test",
        "DATABASE_URL": "sqlite:///:memory:",
        "DEBUG": "True",
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ALLOWED_HOSTS": "127.0.0.1,localhost,testserver",
        "USE_S3_STORAGE": "False",
        "SENTRY_DSN": "",
        "LLM_BACKEND": "none",
        "ANTHROPIC_API_KEY": "",
        "GEMINI_API_KEY": "",
        "GOOGLE_CLIENT_ID": "",
        "GOOGLE_CLIENT_SECRET": "",
        "OLLAMA_BASE_URL": "",
        "VAPID_PUBLIC_KEY": "",
        "VAPID_PRIVATE_KEY": "",
        "PRINT_FANOUT_MQTT_URL": "",
    })

    fixture_settings = importlib.import_module("config.settings_test")
    fixture_settings.DATABASES = {"default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(temporary_root / "fixture.sqlite3"),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {"timeout": 20},
    }}
    # Fresh test databases use current models, matching settings.py's test
    # mode. The historical user-model move prevents fresh normal migrations.
    fixture_settings.MIGRATION_MODULES = {
        app.split(".")[-1]: None for app in fixture_settings.INSTALLED_APPS
    }
    fixture_settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
    fixture_settings.MEDIA_ROOT = temporary_root / "media"
    fixture_settings.STATIC_ROOT = temporary_root / "static"
    fixture_settings.USE_S3_STORAGE = False
    fixture_settings.STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "sprites": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    fixture_settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    fixture_settings.REST_FRAMEWORK = {**fixture_settings.REST_FRAMEWORK, "PAGE_SIZE": 2}
    fixture_settings.LOGGING["root"]["level"] = "WARNING"
    fixture_settings.LOGGING["loggers"]["apps"]["level"] = "WARNING"

    import django

    django.setup()
    from django.core.management import call_command
    from apps.notifications.views import NotificationPagination, NotificationViewSet

    # Only this throwaway process overrides the Inbox to its production page
    # size. Keep habits at 2 so their aggregate-page API contract is exercised.
    class PlayNotificationPagination(NotificationPagination):
        page_size = 20

    NotificationViewSet.pagination_class = PlayNotificationPagination

    call_command("migrate", run_syncdb=True, verbosity=0, interactive=False)


def seed_fixture() -> dict:
    from apps.accounts.models import User
    from apps.achievements.models import Skill, SkillCategory, SkillProgress
    from apps.families.models import Family
    from apps.habits.models import Habit, HabitLog, HabitSkillTag

    CARE_ACTIVITY.clear()
    EXPEDITION_FIXTURE_MOUNT_IDS.clear()
    family = Family.objects.create(name="Unity Test Family", slug="unity-test-family")
    parent = User.objects.create_user(
        username=PARENT_USERNAME, password=PASSWORD, role="parent",
        display_name="Camp Test Parent", family=family,
    )
    family.primary_parent = parent
    family.save(update_fields=["primary_parent"])
    child = User.objects.create_user(
        username=USERNAME, password=PASSWORD, role="child",
        display_name="Camp Explorer", family=family,
    )
    other_family = Family.objects.create(name="Other Test Family", slug="other-test-family")
    other_child = User.objects.create_user(
        username=SECOND_USERNAME, password=PASSWORD, role="child",
        display_name="Second Explorer", family=other_family,
    )

    def habit(name: str, **kwargs):
        return Habit.objects.create(name=name, user=child, created_by=parent, **kwargs)

    available = habit("Read 10 minutes", xp_reward=10, max_taps_per_day=1)
    capped = habit("Daily stretch", xp_reward=5, max_taps_per_day=1, strength=1)
    HabitLog.objects.create(habit=capped, user=child, direction=1)
    negative = habit("Skipping bedtime", habit_type="negative", xp_reward=0)
    pending = Habit.objects.create(
        name="Pending new ritual", user=child, created_by=child,
        pending_parent_review=True,
    )
    inactive = habit("Archived ritual", is_active=False)
    foreign = Habit.objects.create(
        name="Foreign family ritual", user=other_child, created_by=other_child,
    )
    category = SkillCategory.objects.create(name="Prototype Life Skills")
    skill = Skill.objects.create(name="Reading", category=category)
    # The shared journal/meadow preview exercises actual journal XP receipts,
    # which resolve these same writing skills in the production catalog.
    language_arts = SkillCategory.objects.create(name="Language Arts")
    Skill.objects.create(name="Creative Writing", category=language_arts)
    Skill.objects.create(name="Vocabulary", category=language_arts)
    HabitSkillTag.objects.create(habit=available, skill=skill, xp_weight=1)
    SkillProgress.objects.create(user=child, skill=skill, xp_points=95, level=0)
    play = seed_play_account(
        child, parent, balance=120, species_name="Meadow Bird", pet_name="Peep",
        item_names=("Memory Ribbon", "Sunny Seed"), notification_count=3, care=True,
    )
    second_play = seed_play_account(
        other_child, other_child, balance=7, species_name="Dusk Fox", pet_name="Sprout",
        item_names=("Twilight Leaf",), notification_count=1,
    )
    return {
        "username": USERNAME, "password": PASSWORD, "user_id": child.pk,
        "parent_username": PARENT_USERNAME, "parent_password": PASSWORD,
        "second_username": SECOND_USERNAME, "second_password": PASSWORD,
        "second_user_id": other_child.pk,
        "play": play, "second_play": second_play,
        "habits": {
            "available": available.pk, "capped": capped.pk, "negative": negative.pk,
            "pending": pending.pk, "inactive": inactive.pk, "foreign": foreign.pk,
        },
        "skill_id": skill.pk, "initial_skill_xp": 95, "available_xp_reward": 10,
    }


def seed_play_account(user, actor, *, balance: int, species_name: str, pet_name: str,
                      item_names: tuple[str, ...], notification_count: int, care: bool = False) -> dict:
    """Real owned rows and ledger history; nothing relies on UI demo ownership."""
    from django.utils.text import slugify
    from django.utils import timezone
    from datetime import timedelta
    from apps.notifications.models import NotificationType
    from apps.notifications.services import notify
    from apps.pets.models import MountExpedition, PetSpecies, PotionType, UserMount, UserPet
    from apps.rewards.models import CoinLedger
    from apps.rewards.services import CoinService
    from apps.rpg.constants import TriggerType
    from apps.rpg.models import CharacterProfile, DropLog, DropTable, ItemDefinition, UserInventory

    CoinService.award_coins(
        user, balance, CoinLedger.Reason.ADJUSTMENT,
        description="Disposable Play fixture balance", created_by=actor,
    )
    # A real expedition claim invokes the ordinary game loop. Seed an existing
    # check-in today so its first-activity bonus is separate from expedition loot.
    CharacterProfile.objects.filter(user=user).update(last_active_date=timezone.localdate(), login_streak=1)
    species = PetSpecies.objects.create(
        name=species_name, slug=slugify(species_name), icon="*",
        description="A creature owned only inside the disposable Play fixture.",
    )
    potion = PotionType.objects.create(name=f"{pet_name} Cloud", slug=f"{user.username}-cloud")
    mount_potion = PotionType.objects.create(name=f"{pet_name} Sun", slug=f"{user.username}-sun")
    species.available_potions.add(potion, mount_potion)
    pet = UserPet.objects.create(
        user=user, species=species, potion=potion, name=pet_name,
        growth_points=75 if care else 35, is_active=True,
    )
    mount = UserMount.objects.create(user=user, species=species, potion=mount_potion)
    second_pet = expedition_mount = None
    if care:
        second_potion = PotionType.objects.create(name=f"{pet_name} Rain", slug=f"{user.username}-rain")
        expedition_potion = PotionType.objects.create(name=f"{pet_name} Star", slug=f"{user.username}-star")
        species.available_potions.add(second_potion, expedition_potion)
        second_pet = UserPet.objects.create(
            user=user, species=species, potion=second_potion, name="Pip", growth_points=35,
        )
        expedition_mount = UserMount.objects.create(user=user, species=species, potion=expedition_potion)
        MountExpedition.objects.create(
            mount=expedition_mount, tier=MountExpedition.Tier.SHORT,
            returns_at=timezone.now() + timedelta(hours=2), loot={"coins": 15, "items": []},
        )
    drops, food_ids = [], []
    for index, name in enumerate(item_names):
        item = ItemDefinition.objects.create(
            name=name, slug=f"{user.username}-item-{index}", icon="*",
            item_type=ItemDefinition.ItemType.FOOD,
            rarity="rare" if index == 0 else "common", food_species=species,
        )
        UserInventory.objects.create(user=user, item=item, quantity=4 if care and index == 0 else index + 1)
        food_ids.append(item.pk)
        drop = DropLog.objects.create(
            user=user, item=item, trigger_type="chore_complete", quantity=index + 1,
        )
        drops.append(drop.pk)
    hatch_species = PetSpecies.objects.create(
        name="Moonlit Owl" if care else "Dusk Owl", slug=f"{user.username}-hatch-owl", icon="*",
        description="A hatchable creature from this disposable family's inventory.",
    )
    hatch_egg = ItemDefinition.objects.create(
        name="Moonlit Egg" if care else "Dusk Egg", slug=f"{user.username}-hatch-egg", icon="*",
        item_type=ItemDefinition.ItemType.EGG, pet_species=hatch_species,
    )
    UserInventory.objects.create(user=user, item=hatch_egg, quantity=3 if care else 1)
    hatch_potion_ids = []
    for index, variant in enumerate(("Dawn", "Twilight", "Starlight") if care else ("Dusk",)):
        hatch_potion = PotionType.objects.create(name=f"{variant} Glow", slug=f"{user.username}-{variant.lower()}-glow")
        hatch_species.available_potions.add(hatch_potion)
        hatch_item = ItemDefinition.objects.create(
            name=f"{variant} Potion", slug=f"{user.username}-{variant.lower()}-potion", icon="*",
            item_type=ItemDefinition.ItemType.POTION, potion_type=hatch_potion,
        )
        UserInventory.objects.create(user=user, item=hatch_item, quantity=2 if care and index == 0 else 1)
        hatch_potion_ids.append(hatch_item.pk)
    loot_item, _ = ItemDefinition.objects.get_or_create(
        slug="fixture-trail-keepsake", defaults={
            "name": "Trail Keepsake", "icon": "*", "item_type": ItemDefinition.ItemType.FOOD,
            "description": "A returned expedition item in the disposable fixture.", "rarity": "common",
        },
    )
    DropTable.objects.get_or_create(trigger_type=TriggerType.EXPEDITION_RETURNED, item=loot_item, defaults={"weight": 1})
    ready_potion = PotionType.objects.create(name=f"{pet_name} Tide", slug=f"{user.username}-tide")
    species.available_potions.add(ready_potion)
    ready_mount = UserMount.objects.create(user=user, species=species, potion=ready_potion)
    now = timezone.now()
    ready_expedition = MountExpedition.objects.create(
        mount=ready_mount, tier=MountExpedition.Tier.STANDARD,
        started_at=now - timedelta(hours=5), returns_at=now - timedelta(hours=1),
        loot={"coins": 35, "items": [{
            "item_id": loot_item.pk, "quantity": 2, "name": loot_item.name,
            "icon": loot_item.icon, "rarity": loot_item.rarity,
            "item_type": loot_item.item_type, "sprite_key": loot_item.sprite_key,
        }]},
    )
    cooldown_mount = held_mount = None
    if care:
        cooldown_potion = PotionType.objects.create(name=f"{pet_name} Stone", slug=f"{user.username}-stone")
        held_potion = PotionType.objects.create(name=f"{pet_name} Trail", slug=f"{user.username}-trail")
        species.available_potions.add(cooldown_potion, held_potion)
        cooldown_mount = UserMount.objects.create(user=user, species=species, potion=cooldown_potion)
        held_mount = UserMount.objects.create(user=user, species=species, potion=held_potion)
        MountExpedition.objects.create(
            mount=cooldown_mount, tier=MountExpedition.Tier.SHORT, status=MountExpedition.Status.CLAIMED,
            started_at=now, returns_at=now, claimed_at=now, loot={"coins": 0, "items": []},
        )
        EXPEDITION_FIXTURE_MOUNT_IDS.update((mount.pk, held_mount.pk))
    # Older read history exceeds the production-sized Inbox page; all three
    # actionable unread items remain newest on the first page.
    for index in range(22 if notification_count > 1 else 1):
        read = notify(user, f"Earlier memory {index + 1}", notification_type=NotificationType.JOURNAL_REPLY,
                      link="/chronicle?tab=journal")
        read.is_read = True
        read.created_at = timezone.now() - timedelta(days=2, minutes=index)
        read.save(update_fields=["is_read", "created_at"])
    notifications = []
    for index in range(notification_count):
        row = notify(
            user, f"{pet_name} update {index + 1}",
            message="A saved notification from the disposable fixture.",
            notification_type=NotificationType.DROP_RECEIVED,
            link="/treasury?tab=satchel",
        )
        notifications.append(row.pk)
    return {
        "balance": balance, "pet_id": pet.pk, "pet_name": pet_name,
        "mount_id": mount.pk, "species_name": species_name,
        "drop_ids": drops, "notification_ids": notifications,
        "mark_read_id": notifications[-1], "unread_count": notification_count,
        "food_item_ids": food_ids, "initial_growth": pet.growth_points,
        "second_pet_id": second_pet.pk if second_pet else None,
        "expedition_mount_id": expedition_mount.pk if expedition_mount else None,
        "hatch_egg_item_id": hatch_egg.pk, "hatch_potion_item_ids": hatch_potion_ids,
        "ready_mount_id": ready_mount.pk, "ready_expedition_id": ready_expedition.pk,
        "cooldown_mount_id": cooldown_mount.pk if cooldown_mount else None,
        "held_mount_id": held_mount.pk if held_mount else None, "expedition_loot_item_id": loot_item.pk,
    }


def play_state() -> dict:
    """Test instrumentation only: exact persisted effects of viewing Play."""
    from apps.accounts.models import User
    from apps.achievements.models import SkillProgress
    from apps.notifications.models import Notification
    from apps.pets.models import MountExpedition, UserMount, UserPet
    from apps.rewards.models import CoinLedger
    from apps.rewards.services import CoinService
    from apps.rpg.models import DropLog, UserInventory

    accounts = []
    for username in (USERNAME, SECOND_USERNAME):
        user = User.objects.get(username=username)
        accounts.append({
            "user_id": user.pk,
            "balance": CoinService.get_balance(user),
            "ledger_ids": list(CoinLedger.objects.filter(user=user).order_by("id").values_list("id", flat=True)),
            "ledger": list(CoinLedger.objects.filter(user=user).order_by("id").values("id", "amount", "reason")),
            "drop_ids": list(DropLog.objects.filter(user=user).order_by("id").values_list("id", flat=True)),
            "inventory_quantity": sum(UserInventory.objects.filter(user=user).values_list("quantity", flat=True)),
            "skill_xp": sum(SkillProgress.objects.filter(user=user).values_list("xp_points", flat=True)),
            "notification_count": Notification.objects.filter(user=user).count(),
            "unread_ids": list(Notification.objects.filter(user=user, is_read=False).order_by("id").values_list("id", flat=True)),
            "pets": list(UserPet.objects.filter(user=user).order_by("id").values(
                "id", "growth_points", "is_active", "evolved_to_mount", "species_id", "potion_id",
            )),
            "mounts": [{"id": row.pk, "is_active": row.is_active, "potion_name": row.potion.name}
                       for row in UserMount.objects.filter(user=user).select_related("potion").order_by("id")],
            "expeditions": [{
                "id": row.pk, "mount_id": row.mount_id, "tier": row.tier, "status": row.status,
                "started_at": row.started_at.isoformat(), "returns_at": row.returns_at.isoformat(),
                "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
                "is_ready": row.is_ready, "loot": row.loot,
            } for row in MountExpedition.objects.filter(mount__user=user).order_by("id")],
            "food": list(UserInventory.objects.filter(
                user=user, item__item_type="food",
            ).order_by("item_id").values("item_id", "quantity")),
            "items": [{
                "item_id": row["item_id"], "quantity": row["quantity"],
                "item_type": row["item__item_type"], "name": row["item__name"],
            } for row in UserInventory.objects.filter(user=user).order_by("item_id").values(
                "item_id", "quantity", "item__item_type", "item__name",
            )],
            "feed_requests": CARE_ACTIVITY.get(user.pk, {}).get("feed_requests", 0),
            "feed_commits": CARE_ACTIVITY.get(user.pk, {}).get("feed_commits", 0),
            "hatch_requests": CARE_ACTIVITY.get(user.pk, {}).get("hatch_requests", 0),
            "hatch_commits": CARE_ACTIVITY.get(user.pk, {}).get("hatch_commits", 0),
            "expedition_start_requests": CARE_ACTIVITY.get(user.pk, {}).get("expedition_start_requests", 0),
            "expedition_start_commits": CARE_ACTIVITY.get(user.pk, {}).get("expedition_start_commits", 0),
            "expedition_claim_requests": CARE_ACTIVITY.get(user.pk, {}).get("expedition_claim_requests", 0),
            "expedition_claim_commits": CARE_ACTIVITY.get(user.pk, {}).get("expedition_claim_commits", 0),
            "care_responses_pending": CARE_ACTIVITY.get(user.pk, {}).get("care_responses_pending", 0),
            "care_hold_timeouts": CARE_ACTIVITY.get(user.pk, {}).get("care_hold_timeouts", 0),
        })
    return {"accounts": accounts}


def fixture_wsgi(application, *, fail_first_log: bool = False, fail_first_mark_read: bool = False,
                 fail_first_feed_after_commit: bool = False, fail_first_hatch_after_commit: bool = False,
                 fail_first_start_after_commit: bool = False, fail_first_claim_after_commit: bool = False):
    """Local instrumentation, including lost acknowledgements after real care saves."""
    failure_pending = fail_first_log
    read_failure_pending = fail_first_mark_read
    feed_failure_pending = fail_first_feed_after_commit
    hatch_failure_pending = fail_first_hatch_after_commit
    start_failure_pending = fail_first_start_after_commit
    claim_failure_pending = fail_first_claim_after_commit
    care_hold = None
    hold_next_care = False
    hold_lock = Lock()

    def wrapped(environ, start_response):
        nonlocal failure_pending, read_failure_pending, feed_failure_pending, hatch_failure_pending, start_failure_pending, claim_failure_pending, care_hold, hold_next_care
        finish = re.fullmatch(r"/__fixture/finish-expedition/([0-9]+)/", environ.get("PATH_INFO", ""))
        if environ.get("REQUEST_METHOD") == "POST" and finish:
            from datetime import timedelta
            from django.utils import timezone
            from apps.pets.models import MountExpedition

            row = MountExpedition.objects.filter(
                pk=int(finish[1]), mount_id__in=EXPEDITION_FIXTURE_MOUNT_IDS, status=MountExpedition.Status.ACTIVE,
            ).first()
            if row is None:
                body = b'{"error":"This expedition is not a designated active fixture expedition."}'
                start_response("404 Not Found", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
                return [body]
            row.returns_at = max(row.started_at, timezone.now() - timedelta(seconds=1))
            row.save(update_fields=["returns_at", "updated_at"])
            body = json.dumps({"expedition_id": row.pk, "ready": True}).encode()
            start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
            return [body]
        if environ.get("REQUEST_METHOD") == "POST" and environ.get("PATH_INFO") in (
            "/__fixture/hold-next-care/", "/__fixture/delay-next-care/",
        ):
            # One bounded rendezvous, exposed only by the disposable loopback
            # server. A slow client cannot miss a fixed two-second observation.
            with hold_lock:
                if care_hold is not None:
                    body = b'{"error":"A care acknowledgement is already armed or held."}'
                    start_response("409 Conflict", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
                    return [body]
                care_hold = Event()
                hold_next_care = True
            start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", "14")])
            return [b'{"armed":true}']
        if environ.get("REQUEST_METHOD") == "POST" and environ.get("PATH_INFO") == "/__fixture/release-care/":
            with hold_lock:
                if care_hold is None or hold_next_care:
                    body = b'{"error":"No committed care acknowledgement is held."}'
                    start_response("409 Conflict", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
                    return [body]
                care_hold.set()
            body = b'{"released":true}'
            start_response("200 OK", [("Content-Type", "application/json"), ("Content-Length", str(len(body)))])
            return [body]
        if environ.get("REQUEST_METHOD") == "GET" and environ.get("PATH_INFO") == "/__fixture/play-state/":
            body = json.dumps(play_state()).encode()
            start_response("200 OK", [
                ("Content-Type", "application/json"), ("Content-Length", str(len(body))),
                ("Cache-Control", "no-store"),
            ])
            return [body]
        if (
            read_failure_pending and environ.get("REQUEST_METHOD") == "POST"
            and re.fullmatch(r"/api/notifications/[0-9]+/mark_read/", environ.get("PATH_INFO", ""))
        ):
            read_failure_pending = False
            body = json.dumps({"error": "Temporary test transport failure. Try marking this read again."}).encode()
            start_response("503 Service Unavailable", [
                ("Content-Type", "application/json"), ("Content-Length", str(len(body))),
            ])
            return [body]
        if (
            failure_pending
            and environ.get("REQUEST_METHOD") == "POST"
            and re.fullmatch(r"/api/habits/[0-9]+/log/", environ.get("PATH_INFO", ""))
        ):
            failure_pending = False
            body = json.dumps({"error": "Temporary test transport failure. Refresh before retrying."}).encode()
            start_response("503 Service Unavailable", [
                ("Content-Type", "application/json"), ("Content-Length", str(len(body))),
            ])
            return [body]
        path = environ.get("PATH_INFO", "")
        feed = environ.get("REQUEST_METHOD") == "POST" and re.fullmatch(r"/api/pets/[0-9]+/feed/", path)
        hatch = environ.get("REQUEST_METHOD") == "POST" and path == "/api/pets/hatch/"
        start = environ.get("REQUEST_METHOD") == "POST" and re.fullmatch(r"/api/mounts/[0-9]+/expedition/", path)
        claim = environ.get("REQUEST_METHOD") == "POST" and re.fullmatch(r"/api/expeditions/[0-9]+/claim/", path)
        care = feed or hatch or start or claim or (environ.get("REQUEST_METHOD") == "POST" and re.fullmatch(r"/api/(pets|mounts)/[0-9]+/activate/", path))
        if care:
            from rest_framework.authtoken.models import Token

            token = environ.get("HTTP_AUTHORIZATION", "").removeprefix("Token ")
            user_id = Token.objects.filter(key=token).values_list("user_id", flat=True).first()
            activity = CARE_ACTIVITY.setdefault(user_id, {}) if user_id is not None else {}
            if feed:
                activity["feed_requests"] = activity.get("feed_requests", 0) + 1
            if hatch:
                activity["hatch_requests"] = activity.get("hatch_requests", 0) + 1
            if start:
                activity["expedition_start_requests"] = activity.get("expedition_start_requests", 0) + 1
            if claim:
                activity["expedition_claim_requests"] = activity.get("expedition_claim_requests", 0) + 1
            captured = []

            def capture_response(status, headers, _exc_info=None):
                captured.append((status, headers))

            response = application(environ, capture_response)
            try:
                content = b"".join(response)
            finally:
                if hasattr(response, "close"):
                    response.close()
            status, headers = captured[0]
            committed = status.startswith("2")
            if feed and committed:
                activity["feed_commits"] = activity.get("feed_commits", 0) + 1
            if hatch and committed:
                activity["hatch_commits"] = activity.get("hatch_commits", 0) + 1
            if start and committed:
                activity["expedition_start_commits"] = activity.get("expedition_start_commits", 0) + 1
            if claim and committed and json.loads(content).get("freshly_claimed") is True:
                activity["expedition_claim_commits"] = activity.get("expedition_claim_commits", 0) + 1
            held = None
            if committed:
                with hold_lock:
                    if hold_next_care:
                        held = care_hold
                        hold_next_care = False
            if held is not None:
                activity["care_responses_pending"] = activity.get("care_responses_pending", 0) + 1
                try:
                    released = held.wait(timeout=15)
                    if not released:
                        activity["care_hold_timeouts"] = activity.get("care_hold_timeouts", 0) + 1
                        content = b'{"error":"The fixture care acknowledgement hold expired without release."}'
                        status = "503 Service Unavailable"
                        headers = [("Content-Type", "application/json"), ("Content-Length", str(len(content)))]
                finally:
                    activity["care_responses_pending"] -= 1
                    with hold_lock:
                        if care_hold is held:
                            care_hold = None
            if feed and committed and feed_failure_pending:
                feed_failure_pending = False
                content = json.dumps({"error": "The test server committed this feed but lost its acknowledgement. Refresh and check before feeding again."}).encode()
                status = "503 Service Unavailable"
                headers = [("Content-Type", "application/json"), ("Content-Length", str(len(content)))]
            if hatch and committed and hatch_failure_pending:
                hatch_failure_pending = False
                content = json.dumps({"error": "The test server committed this hatch but lost its acknowledgement. Refresh and check before hatching again."}).encode()
                status = "503 Service Unavailable"
                headers = [("Content-Type", "application/json"), ("Content-Length", str(len(content)))]
            if start and committed and start_failure_pending:
                start_failure_pending = False
                content = b'{"error":"The fixture committed this expedition start but lost its acknowledgement. Refresh and check before sending again."}'
                status = "503 Service Unavailable"
                headers = [("Content-Type", "application/json"), ("Content-Length", str(len(content)))]
            if claim and committed and claim_failure_pending and json.loads(content).get("freshly_claimed") is True:
                claim_failure_pending = False
                content = b'{"error":"The fixture committed this expedition claim but lost its acknowledgement. Refresh and check the recorded loot."}'
                status = "503 Service Unavailable"
                headers = [("Content-Type", "application/json"), ("Content-Length", str(len(content)))]
            start_response(status, headers)
            return [content]
        return application(environ, start_response)

    return wrapped


def check_fixture(fixture: dict, *, fail_first_log: bool = False, fail_first_mark_read: bool = False,
                  fail_first_feed_after_commit: bool = False, fail_first_hatch_after_commit: bool = False,
                  fail_first_start_after_commit: bool = False, fail_first_claim_after_commit: bool = False) -> None:
    """Exercise real view/serializer/award paths on the isolated database."""
    from apps.achievements.models import SkillProgress
    from django.core.wsgi import get_wsgi_application
    from django.test import RequestFactory
    from rest_framework.test import APIClient

    client = APIClient()
    current_token = ""
    application = fixture_wsgi(get_wsgi_application(), fail_first_log=fail_first_log,
                               fail_first_mark_read=fail_first_mark_read,
                               fail_first_feed_after_commit=fail_first_feed_after_commit,
                               fail_first_hatch_after_commit=fail_first_hatch_after_commit,
                               fail_first_start_after_commit=fail_first_start_after_commit,
                               fail_first_claim_after_commit=fail_first_claim_after_commit)

    def login(username: str):
        nonlocal current_token
        response = client.post("/api/auth/", {
            "action": "login", "username": username, "password": PASSWORD,
        }, format="json")
        assert response.status_code == 200, response.content
        current_token = response.data["token"]
        client.credentials(HTTP_AUTHORIZATION=f"Token {current_token}")

    def log_request(key: str, *, pending: bool = False):
        path = f"/api/habits/{fixture['habits'][key]}/log/" + ("?pending=true" if pending else "")
        return post_request(path, {"direction": 1})

    def post_request(path: str, data: dict):
        request = RequestFactory().post(
            path, json.dumps(data), content_type="application/json",
            HTTP_AUTHORIZATION=f"Token {current_token}",
        )
        statuses = []

        def start_response(status, _headers, _exc_info=None):
            statuses.append(int(status.split()[0]))

        response = application(request.environ, start_response)
        try:
            content = b"".join(response)
        finally:
            if hasattr(response, "close"):
                response.close()
        return SimpleNamespace(status_code=statuses[0], content=content, data=json.loads(content))

    def collect_rows(path: str):
        rows = []
        visited = set()
        while path:
            assert path not in visited, "Pagination cycle"
            visited.add(path)
            response = client.get(path)
            assert response.status_code == 200, response.content
            page = response.json()
            rows.extend(page["results"])
            next_url = page["next"]
            if not next_url:
                break
            parsed = urlsplit(next_url)
            assert parsed.netloc in ("", "testserver"), "Unexpected pagination origin"
            path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        return rows

    login(USERNAME)
    before = play_state()
    coins = client.get("/api/coins/").json()
    assert coins["balance"] == fixture["play"]["balance"]
    drops = client.get("/api/drops/recent/").json()
    assert {row["id"] for row in drops} == set(fixture["play"]["drop_ids"])
    stable = client.get("/api/pets/stable/").json()
    assert {row["id"] for row in stable["pets"]} == {fixture["play"]["pet_id"], fixture["play"]["second_pet_id"]}
    assert {row["id"] for row in stable["mounts"]} == {
        fixture["play"][key] for key in ("mount_id", "expedition_mount_id", "ready_mount_id", "cooldown_mount_id", "held_mount_id")
    }
    notification_page = client.get("/api/notifications/").json()
    assert notification_page["count"] == 25 and len(notification_page["results"]) == 20 and notification_page["next"]
    notifications = collect_rows("/api/notifications/")
    assert {row["id"] for row in notifications if not row["is_read"]} == set(fixture["play"]["notification_ids"])
    assert play_state() == before, "Opening rewards/inbox/stable must not award or consume anything"
    mark_id = fixture["play"]["mark_read_id"]
    mark_request = RequestFactory().post(
        f"/api/notifications/{mark_id}/mark_read/", "{}", content_type="application/json",
        HTTP_AUTHORIZATION=f"Token {current_token}",
    )
    statuses = []
    response = application(mark_request.environ, lambda status, _headers: statuses.append(int(status.split()[0])))
    try:
        body = b"".join(response)
    finally:
        if hasattr(response, "close"):
            response.close()
    assert statuses == ([503] if fail_first_mark_read else [200]), body
    if fail_first_mark_read:
        assert play_state() == before, "Transport rejection must leave the notification unread"
    confirmed = client.post(f"/api/notifications/{mark_id}/mark_read/", {}, format="json")
    assert confirmed.status_code == 200 and confirmed.data["is_read"] is True
    assert client.get("/api/notifications/unread_count/").json()["count"] == 2
    assert client.post(f"/api/notifications/{mark_id}/mark_read/", {}, format="json").status_code == 200
    foreign_read = client.post(f"/api/notifications/{fixture['second_play']['mark_read_id']}/mark_read/", {}, format="json")
    assert foreign_read.status_code == 404, foreign_read.content
    after_read = play_state()
    after_read["accounts"][0]["unread_ids"] = before["accounts"][0]["unread_ids"]
    assert after_read == before, "Marking one notification read must not award anything"

    pet_id = fixture["play"]["pet_id"]
    food_id = fixture["play"]["food_item_ids"][0]
    food = client.get("/api/inventory/").json()
    assert next(row for row in food if row["item"]["id"] == food_id)["quantity"] == 4
    failed_or_confirmed = post_request(f"/api/pets/{pet_id}/feed/", {"food_item_id": food_id})
    assert failed_or_confirmed.status_code == (503 if fail_first_feed_after_commit else 200)
    first_feed = play_state()["accounts"][0]
    assert first_feed["feed_requests"] == first_feed["feed_commits"] == 1
    assert next(row for row in first_feed["pets"] if row["id"] == pet_id)["growth_points"] == 90
    assert next(row for row in first_feed["food"] if row["item_id"] == food_id)["quantity"] == 3
    client.get("/api/pets/stable/")
    client.get("/api/inventory/")
    assert play_state()["accounts"][0] == first_feed, "Refreshing interrupted care never repeats the feed"
    confirmed_feed = post_request(f"/api/pets/{pet_id}/feed/", {"food_item_id": food_id})
    assert confirmed_feed.status_code == 200 and confirmed_feed.data["evolved"] is True
    assert confirmed_feed.data["new_growth"] == 100 and confirmed_feed.data["mount_id"] > 0
    second_feed = play_state()["accounts"][0]
    assert second_feed["feed_requests"] == second_feed["feed_commits"] == 2
    assert next(row for row in second_feed["food"] if row["item_id"] == food_id)["quantity"] == 2
    assert next(row for row in second_feed["pets"] if row["id"] == pet_id)["evolved_to_mount"] is True
    assert len(second_feed["mounts"]) == len(first_feed["mounts"]) + 1
    assert (second_feed["balance"], second_feed["ledger_ids"], second_feed["drop_ids"], second_feed["skill_xp"]) == (
        first_feed["balance"], first_feed["ledger_ids"], first_feed["drop_ids"], first_feed["skill_xp"],
    ), "Care consumes the requested food and changes growth, without inventing XP or rewards"
    assert client.post(f"/api/pets/{pet_id}/feed/", {"food_item_id": food_id}, format="json").status_code == 400
    active_pet_id = fixture["play"]["second_pet_id"]
    assert client.post(f"/api/pets/{active_pet_id}/activate/", {}, format="json").data["is_active"] is True
    assert client.post(f"/api/mounts/{fixture['play']['mount_id']}/activate/", {}, format="json").data["is_active"] is True
    foreign_pet_id = fixture["second_play"]["pet_id"]
    assert client.post(f"/api/pets/{foreign_pet_id}/feed/", {"food_item_id": food_id}, format="json").status_code == 400
    assert play_state()["accounts"][1] == before["accounts"][1], "Care cannot change another family's pet or inventory"
    hatch_before = play_state()
    egg_id = fixture["play"]["hatch_egg_item_id"]
    potion_ids = fixture["play"]["hatch_potion_item_ids"]
    hatch_body = {"egg_item_id": egg_id, "potion_item_id": potion_ids[0]}
    hatched = post_request("/api/pets/hatch/", hatch_body)
    assert hatched.status_code == (503 if fail_first_hatch_after_commit else 201), hatched.content
    first_hatch = play_state()["accounts"][0]
    assert first_hatch["hatch_requests"] == first_hatch["hatch_commits"] == 1
    assert len(first_hatch["pets"]) == len(hatch_before["accounts"][0]["pets"]) + 1
    assert next(row for row in first_hatch["items"] if row["item_id"] == egg_id)["quantity"] == 2
    assert next(row for row in first_hatch["items"] if row["item_id"] == potion_ids[0])["quantity"] == 1
    client.get("/api/pets/stable/")
    client.get("/api/inventory/")
    assert play_state()["accounts"][0] == first_hatch, "Refreshing an interrupted hatch never consumes another pair"
    duplicate = post_request("/api/pets/hatch/", hatch_body)
    assert duplicate.status_code == 400 and "already have" in duplicate.data["error"], duplicate.content
    duplicate_state = play_state()["accounts"][0]
    assert duplicate_state["hatch_requests"] == 2 and duplicate_state["hatch_commits"] == 1
    assert duplicate_state["items"] == first_hatch["items"] and duplicate_state["pets"] == first_hatch["pets"]
    foreign_before = play_state()
    for foreign_body in (
        {"egg_item_id": fixture["second_play"]["hatch_egg_item_id"], "potion_item_id": potion_ids[1]},
        {"egg_item_id": egg_id, "potion_item_id": fixture["second_play"]["hatch_potion_item_ids"][0]},
    ):
        foreign = client.post("/api/pets/hatch/", foreign_body, format="json")
        assert foreign.status_code == 400, foreign.content
    assert play_state() == foreign_before, "Foreign-family eggs and potions cannot be consumed"
    for potion_id in potion_ids[1:]:
        if potion_id == potion_ids[-1]:
            # Exercise the actual threaded HTTP server: a snapshot must expose
            # the committed hatch while the original acknowledgement is held.
            with make_server("127.0.0.1", 0, application, server_class=DisposableFixtureServer) as probe_server:
                server_thread = Thread(target=probe_server.serve_forever, kwargs={"poll_interval": .05})
                server_thread.start()
                probe_origin = f"http://127.0.0.1:{probe_server.server_port}"
                result, errors = [], []

                def probe(path: str, data: dict | None = None):
                    request = Request(probe_origin + path, data=json.dumps(data).encode() if data is not None else None,
                                      headers={"Content-Type": "application/json", "Authorization": f"Token {current_token}"})
                    with urlopen(request, timeout=10) as response:
                        content = response.read()
                        return SimpleNamespace(status_code=response.status, content=content, data=json.loads(content))

                def request_held_hatch():
                    try:
                        result.append(probe("/api/pets/hatch/", {"egg_item_id": egg_id, "potion_item_id": potion_id}))
                    except Exception as error:
                        errors.append(error)

                request_thread = Thread(target=request_held_hatch)
                release_sent = False
                try:
                    assert probe("/__fixture/hold-next-care/", {}).data["armed"] is True
                    request_thread.start()
                    observation_deadline = time.monotonic() + 5
                    held_state = None
                    while time.monotonic() < observation_deadline:
                        held_state = probe("/__fixture/play-state/").data["accounts"][0]
                        if held_state["care_responses_pending"] == 1:
                            break
                    assert held_state["care_responses_pending"] == 1 and request_thread.is_alive(), "Snapshot GET must observe the held acknowledgement"
                    assert held_state["hatch_requests"] == 4 and held_state["hatch_commits"] == 3
                    assert held_state["care_hold_timeouts"] == 0 and len(held_state["pets"]) == len(hatch_before["accounts"][0]["pets"]) + 3
                    assert probe("/__fixture/release-care/", {}).data["released"] is True
                    release_sent = True
                    request_thread.join(timeout=5)
                    assert not request_thread.is_alive() and not errors and len(result) == 1, "Explicit release must drain the held hatch response"
                    drained = probe("/__fixture/play-state/").data["accounts"][0]
                    assert drained["care_responses_pending"] == 0 and drained["care_hold_timeouts"] == 0
                    confirmed_hatch = result[0]
                finally:
                    try:
                        if request_thread.is_alive() and not release_sent:
                            try:
                                probe("/__fixture/release-care/", {})
                            except Exception:
                                # An expired fixture hold will reject release;
                                # preserve the original assertion and stop safely.
                                pass
                            request_thread.join(timeout=5)
                    finally:
                        probe_server.shutdown()
                        server_thread.join(timeout=5)
        else:
            confirmed_hatch = post_request("/api/pets/hatch/", {"egg_item_id": egg_id, "potion_item_id": potion_id})
        assert confirmed_hatch.status_code == 201, confirmed_hatch.content
        assert confirmed_hatch.data["growth_points"] == 0 and not confirmed_hatch.data["is_active"]
        assert not confirmed_hatch.data["evolved_to_mount"] and not confirmed_hatch.data["is_fully_grown"]
    final_hatch = play_state()["accounts"][0]
    assert final_hatch["hatch_requests"] == 4 and final_hatch["hatch_commits"] == 3
    assert final_hatch["inventory_quantity"] == hatch_before["accounts"][0]["inventory_quantity"] - 6
    assert all(row["item_id"] != egg_id and row["item_id"] not in potion_ids[1:] for row in final_hatch["items"])
    exhausted = client.post("/api/pets/hatch/", {"egg_item_id": egg_id, "potion_item_id": potion_ids[0]}, format="json")
    assert exhausted.status_code == 400, exhausted.content
    assert play_state()["accounts"][0] == final_hatch, "An exhausted egg cannot create another pet"
    assert (final_hatch["balance"], final_hatch["ledger_ids"], final_hatch["drop_ids"], final_hatch["skill_xp"]) == (
        hatch_before["accounts"][0]["balance"], hatch_before["accounts"][0]["ledger_ids"],
        hatch_before["accounts"][0]["drop_ids"], hatch_before["accounts"][0]["skill_xp"],
    ), "Hatching consumes a pair and creates a pet without inventing XP, coins or drops"
    assert play_state()["accounts"][1] == hatch_before["accounts"][1], "Hatching cannot change another family's creatures or items"
    expedition_before = play_state()
    listed = client.get("/api/expeditions/").json()["expeditions"]
    ready = client.get("/api/expeditions/?ready=true").json()["expeditions"]
    assert {row["id"] for row in listed} == {row["id"] for row in expedition_before["accounts"][0]["expeditions"]}
    assert [row["id"] for row in ready] == [fixture["play"]["ready_expedition_id"]]
    assert play_state() == expedition_before, "Expedition lists/countdowns must not start or claim anything"
    free_mount_id = fixture["play"]["mount_id"]
    started = post_request(f"/api/mounts/{free_mount_id}/expedition/", {"tier": "short"})
    assert started.status_code == (503 if fail_first_start_after_commit else 201), started.content
    start_state = play_state()
    first_expedition = next(row for row in start_state["accounts"][0]["expeditions"] if row["mount_id"] == free_mount_id)
    assert first_expedition["tier"] == "short" and first_expedition["status"] == "active" and not first_expedition["is_ready"]
    assert start_state["accounts"][0]["expedition_start_requests"] == start_state["accounts"][0]["expedition_start_commits"] == 1
    for key in ("balance", "ledger_ids", "drop_ids", "items", "skill_xp"):
        assert start_state["accounts"][0][key] == expedition_before["accounts"][0][key], "Starting is not a loot payout"
    client.get("/api/expeditions/")
    client.get("/api/pets/stable/")
    client.get("/api/inventory/")
    assert play_state() == start_state, "Interrupted start refresh never sends another mount"
    for mount_id, expected_status in (
        (free_mount_id, 400), (fixture["play"]["cooldown_mount_id"], 400),
        (fixture["second_play"]["mount_id"], 404),
    ):
        rejected = client.post(f"/api/mounts/{mount_id}/expedition/", {"tier": "short"}, format="json")
        assert rejected.status_code == expected_status, rejected.content
    early = client.post(f"/api/expeditions/{first_expedition['id']}/claim/", {}, format="json")
    foreign_claim = client.post(f"/api/expeditions/{fixture['second_play']['ready_expedition_id']}/claim/", {}, format="json")
    assert early.status_code == 400 and foreign_claim.status_code == 404
    assert play_state() == start_state, "Active/cooldown/foreign/early gates preserve persisted state"
    finished = post_request(f"/__fixture/finish-expedition/{first_expedition['id']}/", {})
    assert finished.status_code == 200 and finished.data["ready"] is True
    for forbidden_id in (fixture["play"]["ready_expedition_id"], fixture["second_play"]["ready_expedition_id"]):
        assert post_request(f"/__fixture/finish-expedition/{forbidden_id}/", {}).status_code == 404
    ready_before_claim = play_state()
    claimed = post_request(f"/api/expeditions/{first_expedition['id']}/claim/", {})
    assert claimed.status_code == (503 if fail_first_claim_after_commit else 200), claimed.content
    first_claim = play_state()
    first_claim_account = first_claim["accounts"][0]
    expected_coins = first_expedition["loot"]["coins"]
    expected_quantity = sum(slot["quantity"] for slot in first_expedition["loot"]["items"])
    assert first_claim_account["expedition_claim_requests"] == first_claim_account["expedition_claim_commits"] == 1
    assert first_claim_account["balance"] == ready_before_claim["accounts"][0]["balance"] + expected_coins
    assert first_claim_account["inventory_quantity"] == ready_before_claim["accounts"][0]["inventory_quantity"] + expected_quantity
    assert len(first_claim_account["ledger"]) == len(ready_before_claim["accounts"][0]["ledger"]) + 1
    assert first_claim_account["ledger"][-1]["reason"] == "expedition" and first_claim_account["ledger"][-1]["amount"] == expected_coins
    assert first_claim_account["drop_ids"] == ready_before_claim["accounts"][0]["drop_ids"]
    assert first_claim_account["skill_xp"] == ready_before_claim["accounts"][0]["skill_xp"]
    client.get("/api/expeditions/")
    client.get("/api/coins/")
    client.get("/api/inventory/")
    assert play_state() == first_claim, "Interrupted claim refresh never repeats a payout"
    again = post_request(f"/api/expeditions/{first_expedition['id']}/claim/", {})
    assert again.status_code == 200 and again.data["coins_awarded"] == 0 and again.data["freshly_claimed"] is False
    repeated_state = play_state()["accounts"][0]
    assert repeated_state["expedition_claim_requests"] == 2 and repeated_state["expedition_claim_commits"] == 1
    for key in ("balance", "ledger", "drop_ids", "items", "skill_xp", "expeditions"):
        assert repeated_state[key] == first_claim_account[key], "A repeated receipt cannot pay twice"
    confirmed = post_request(f"/api/expeditions/{fixture['play']['ready_expedition_id']}/claim/", {})
    assert confirmed.status_code == 200 and confirmed.data["freshly_claimed"] is True and confirmed.data["coins_awarded"] == 35
    assert confirmed.data["items"][0]["quantity"] == 2
    final_expeditions = play_state()
    assert final_expeditions["accounts"][0]["expedition_claim_requests"] == 3 and final_expeditions["accounts"][0]["expedition_claim_commits"] == 2
    assert final_expeditions["accounts"][0]["balance"] == first_claim_account["balance"] + 35
    assert final_expeditions["accounts"][0]["inventory_quantity"] == first_claim_account["inventory_quantity"] + 2
    assert final_expeditions["accounts"][1] == expedition_before["accounts"][1], "Expeditions preserve the other family's creatures, rewards and history"
    first_page = client.get("/api/habits/").json()
    assert len(first_page["results"]) == 2 and first_page["next"]
    rows = collect_rows("/api/habits/")
    ids = {row["id"] for row in rows}
    assert fixture["habits"]["available"] in ids
    assert fixture["habits"]["capped"] in ids
    assert fixture["habits"]["negative"] in ids
    assert fixture["habits"]["pending"] not in ids
    assert fixture["habits"]["foreign"] not in ids
    character = client.get("/api/character/")
    assert character.status_code == 200, character.content

    if fail_first_log:
        failed = log_request("available")
        assert failed.status_code == 503 and "error" in failed.data, failed.content
        unchanged_rows = collect_rows("/api/habits/")
        unchanged = next(row for row in unchanged_rows if row["id"] == fixture["habits"]["available"])
        assert unchanged["strength"] == 0 and unchanged["taps_today"] == 0
        progress = SkillProgress.objects.get(user_id=fixture["user_id"], skill_id=fixture["skill_id"])
        assert progress.xp_points == 95 and progress.level == 0

    for key, expected_status in [("capped", 400), ("negative", 400), ("foreign", 404)]:
        response = log_request(key)
        assert response.status_code == expected_status, response.content
    pending = log_request("pending", pending=True)
    assert pending.status_code == 400, pending.content
    result = log_request("available")
    assert result.status_code == 200, result.content
    assert result.data["direction"] == 1
    assert result.data["xp_reward"] == 10
    assert result.data["new_strength"] == 1
    assert isinstance(result.data["game_event"], dict), result.content
    progress = SkillProgress.objects.get(user_id=fixture["user_id"], skill_id=fixture["skill_id"])
    assert progress.xp_points == 105 and progress.level == 1
    rows = collect_rows("/api/habits/")
    available = next(row for row in rows if row["id"] == fixture["habits"]["available"])
    assert available["taps_today"] == 1 and available["strength"] == 1
    memory = {"summary": "Synthetic private preview memory.", "client_entry_id": "40f149c3-83ca-428d-a48f-5dca68bf90b9"}
    saved = client.post("/api/chronicle/journal/", memory, format="json")
    assert saved.status_code == 201, saved.content
    assert saved.data["is_private"] is True
    assert saved.data["reward_receipt"]["xp_awarded"] == 15, saved.content
    meadow = client.get("/api/chronicle/meadow/").json()
    assert meadow["keepsake_count"] == 1 and meadow["journal_xp_awarded"] == 15
    assert memory["summary"] not in json.dumps(meadow)
    replay = client.post("/api/chronicle/journal/", memory, format="json")
    assert replay.status_code == 200, replay.content
    assert client.get("/api/chronicle/meadow/").json() == meadow
    login(PARENT_USERNAME)
    parent_rows = collect_rows("/api/habits/")
    assert fixture["habits"]["foreign"] not in {row["id"] for row in parent_rows}
    assert client.get("/api/chronicle/meadow/").status_code == 403
    login(SECOND_USERNAME)
    assert client.get("/api/coins/").json()["balance"] == fixture["second_play"]["balance"]
    second_stable = client.get("/api/pets/stable/").json()
    assert [row["id"] for row in second_stable["pets"]] == [fixture["second_play"]["pet_id"]]
    assert fixture["play"]["pet_id"] not in {row["id"] for row in second_stable["pets"]}
    sys.stdout.write("Fixture checks passed: auth, reward/stable/inbox ownership, view-only awards, explicit mark-read/failure, care consumption, committed feed/hatch/expedition-start/claim acknowledgement loss, growth/evolution, active selection, hatch pair consumption/duplicates/exhaustion/family scope, expedition gates/locked-loot payouts/repeated receipts/family isolation, held acknowledgement with concurrent snapshot and explicit release, pagination, scoped lists, caps, approval, skill XP, journal privacy, receipt replay, persistence.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="Loopback port; 0 chooses a free port.")
    parser.add_argument("--ready-file", type=Path, help="Write URL, test credentials, and fixture IDs as JSON.")
    parser.add_argument("--stop-file", type=Path, help="Stop when this sentinel file exists; remove it on exit.")
    parser.add_argument(
        "--fail-first-log", action="store_true",
        help="Return one fixture HTTP503 before Django receives the first habit-log POST.",
    )
    parser.add_argument("--check", action="store_true", help="Check fixtures through actual Django views and exit.")
    parser.add_argument("--fail-first-mark-read", action="store_true", help="Reject the first notification mark-read POST before Django.")
    parser.add_argument("--fail-first-feed-after-commit", action="store_true", help="Commit the first valid feed, then replace its acknowledgement with HTTP503.")
    parser.add_argument("--fail-first-hatch-after-commit", action="store_true", help="Commit the first valid hatch, then replace its acknowledgement with HTTP503.")
    parser.add_argument("--fail-first-expedition-start-after-commit", "--fail-first-start-after-commit", dest="fail_first_start_after_commit",
                        action="store_true", help="Commit one expedition start, then replace its acknowledgement with HTTP503.")
    parser.add_argument("--fail-first-expedition-claim-after-commit", "--fail-first-claim-after-commit", dest="fail_first_claim_after_commit",
                        action="store_true", help="Materialize one expedition claim, then replace its acknowledgement with HTTP503.")
    parser.add_argument("--lifetime-seconds", type=float, default=1800, help="Auto-stop after this many seconds.")
    args = parser.parse_args()
    if not 0 <= args.port <= 65535 or args.lifetime_seconds <= 0:
        parser.error("port must be 0..65535 and lifetime-seconds must be positive")

    stopping = False
    ready_written = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)

    with TemporaryDirectory(prefix="abby-unity-fixture-") as temporary:
        try:
            configure_django(Path(temporary))
            fixture = seed_fixture()
            fixture["fail_first_log"] = args.fail_first_log
            fixture["fail_first_mark_read"] = args.fail_first_mark_read
            fixture["fail_first_feed_after_commit"] = args.fail_first_feed_after_commit
            fixture["fail_first_hatch_after_commit"] = args.fail_first_hatch_after_commit
            fixture["fail_first_start_after_commit"] = args.fail_first_start_after_commit
            fixture["fail_first_claim_after_commit"] = args.fail_first_claim_after_commit
            if args.check:
                check_fixture(fixture, fail_first_log=args.fail_first_log, fail_first_mark_read=args.fail_first_mark_read,
                              fail_first_feed_after_commit=args.fail_first_feed_after_commit,
                              fail_first_hatch_after_commit=args.fail_first_hatch_after_commit,
                              fail_first_start_after_commit=args.fail_first_start_after_commit,
                              fail_first_claim_after_commit=args.fail_first_claim_after_commit)
                return 0
            from django.core.wsgi import get_wsgi_application

            application = fixture_wsgi(get_wsgi_application(), fail_first_log=args.fail_first_log,
                                       fail_first_mark_read=args.fail_first_mark_read,
                                       fail_first_feed_after_commit=args.fail_first_feed_after_commit,
                                       fail_first_hatch_after_commit=args.fail_first_hatch_after_commit,
                                       fail_first_start_after_commit=args.fail_first_start_after_commit,
                                       fail_first_claim_after_commit=args.fail_first_claim_after_commit)
            with make_server("127.0.0.1", args.port, application, server_class=DisposableFixtureServer) as server:
                server.timeout = 0.25
                fixture["url"] = f"http://127.0.0.1:{server.server_port}"
                fixture["expires_in_seconds"] = args.lifetime_seconds
                ready_json = json.dumps(fixture, indent=2)
                if args.ready_file:
                    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
                    pending_file = args.ready_file.with_name(args.ready_file.name + ".pending")
                    pending_file.write_text(ready_json + "\n", encoding="utf-8")
                    pending_file.replace(args.ready_file)
                    ready_written = True
                sys.stdout.write(ready_json + "\n")
                sys.stdout.flush()
                deadline = time.monotonic() + args.lifetime_seconds
                while (
                    not stopping
                    and time.monotonic() < deadline
                    and not (args.stop_file and args.stop_file.exists())
                ):
                    server.handle_request()
            return 0
        finally:
            from django.db import connections

            connections.close_all()
            if ready_written and args.ready_file.exists():
                args.ready_file.unlink()
            if args.stop_file and args.stop_file.exists():
                args.stop_file.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
