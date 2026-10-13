"""Trusted, narrowly scoped provisioning for deployed browser checks."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from rest_framework.authtoken.models import Token

from .models import Family, LiveTestFamily


BASE_URL = "https://abby.bos.lol"
FAMILY_SLUG = "abby-live-checks"
FAMILY_NAME = "Abby Live Checks"
NAMESPACE = "abby-live-checks-v1"
USERNAMES = {"parent": "abby_loop_parent", "child": "abby_loop_child"}


def read_private_credentials(filename: str) -> dict:
    """Read a bounded, owner-only regular file without following a symlink."""
    if not Path(filename).is_absolute():
        raise CommandError("The credential file must be an absolute private path.")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(filename, flags)
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 8192:
                raise CommandError("The credential file must be a bounded regular file.")
            if os.name == "posix" and (
                stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.geteuid()
            ):
                raise CommandError("The credential file must be owned by this user with mode 0600.")
            payload = json.loads(handle.read(8193))
    except (OSError, UnicodeError, json.JSONDecodeError):
        # Never echo file contents, parser excerpts, passwords or OS errors.
        raise CommandError("The private credential file could not be read.") from None
    return validate_credentials(payload)


def validate_credentials(payload: object) -> dict:
    required = {"schemaVersion", "baseUrl", "familySlug", "parent", "child"}
    if not isinstance(payload, dict) or set(payload) not in (required, required | {"familyId"}):
        raise CommandError("The private credential schema is invalid.")
    if type(payload["schemaVersion"]) is not int or payload["schemaVersion"] != 1:
        raise CommandError("The private credential schema version is unsupported.")
    if payload["baseUrl"] != BASE_URL or payload["familySlug"] != FAMILY_SLUG:
        raise CommandError("The live-test origin or family namespace is not permitted.")
    with_ids = "familyId" in payload
    if with_ids and (type(payload["familyId"]) is not int or payload["familyId"] <= 0):
        raise CommandError("The expected fixture identities are invalid.")
    User = get_user_model()
    for role, username in USERNAMES.items():
        item = payload[role]
        expected = {"username", "password"} | ({"id"} if with_ids else set())
        if not isinstance(item, dict) or set(item) != expected or item["username"] != username:
            raise CommandError("The reserved live-test account schema is invalid.")
        if with_ids and (type(item["id"]) is not int or item["id"] <= 0):
            raise CommandError("The expected fixture identities are invalid.")
        password = item["password"]
        if not isinstance(password, str) or not 16 <= len(password) <= 256:
            raise CommandError("The live-test password does not meet policy.")
        try:
            validate_password(password, user=User(username=username, role=role))
        except ValidationError:
            raise CommandError("The live-test password does not meet policy.") from None
    if with_ids and payload["parent"]["id"] == payload["child"]["id"]:
        raise CommandError("The expected fixture identities must be distinct.")
    return payload


def _seen_flags() -> dict:
    from apps.lorebook.services import load_lorebook_catalog

    # The read-only smoke must not dismiss first-encounter panels with API
    # writes. These flags acknowledge copy only; they award no progression.
    return {f"{entry['slug']}_seen": True for entry in load_lorebook_catalog()}


def _receipt(status: str, family, parent, child) -> dict:
    return {
        "schemaVersion": 1,
        "status": status,
        "baseUrl": BASE_URL,
        "familySlug": FAMILY_SLUG,
        "familyId": family.pk,
        "parent": {"id": parent.pk, "username": USERNAMES["parent"], "role": "parent"},
        "child": {"id": child.pk, "username": USERNAMES["child"], "role": "child"},
    }


def provision_live_test_family(payload: dict, *, rotate_passwords: bool = False) -> dict:
    payload = validate_credentials(payload)
    User = get_user_model()
    flags = _seen_flags()
    try:
        with transaction.atomic():
            owned = LiveTestFamily.objects.select_for_update(of=("self",)).filter(namespace=NAMESPACE).first()
            if owned is None:
                if "familyId" in payload:
                    raise CommandError("Expected fixture identities have no ownership receipt.")
                if Family.objects.filter(slug=FAMILY_SLUG).exists() or User.objects.filter(
                    username__in=USERNAMES.values(),
                ).exists():
                    raise CommandError("Reserved live-test identities already exist without ownership.")
                family = Family.objects.create(name=FAMILY_NAME, slug=FAMILY_SLUG)
                parent = User.objects.create_user(
                    username=USERNAMES["parent"], password=payload["parent"]["password"],
                    role="parent", family=family, is_staff=False, is_superuser=False,
                    display_name="Live Test Parent", hourly_rate=0,
                )
                child = User.objects.create_user(
                    username=USERNAMES["child"], password=payload["child"]["password"],
                    role="child", family=family, is_staff=False, is_superuser=False,
                    display_name="Live Test Child", hourly_rate=0, lorebook_flags=flags,
                )
                family.primary_parent = parent
                family.save(update_fields=["primary_parent"])
                LiveTestFamily.objects.create(namespace=NAMESPACE, family=family, parent=parent, child=child)
                return _receipt("created", family, parent, child)

            family = Family.objects.select_for_update().get(pk=owned.family_id)
            members = list(User.objects.select_for_update().filter(family=family).order_by("pk"))
            by_id = {user.pk: user for user in members}
            if family.slug != FAMILY_SLUG or family.name != FAMILY_NAME or set(by_id) != {
                owned.parent_id, owned.child_id,
            } or family.primary_parent_id != owned.parent_id:
                raise CommandError("Live-test family ownership no longer matches its receipt.")
            parent, child = by_id[owned.parent_id], by_id[owned.child_id]
            for role, user in (("parent", parent), ("child", child)):
                if user.username != USERNAMES[role] or user.role != role or not user.is_active \
                        or user.is_staff or user.is_superuser:
                    raise CommandError("Live-test account ownership or privileges changed.")
                if "familyId" in payload and (
                    payload["familyId"] != family.pk or payload[role]["id"] != user.pk
                ):
                    raise CommandError("Expected live-test identities do not match their ownership receipt.")
            mismatched = [user for role, user in (("parent", parent), ("child", child))
                          if not check_password(payload[role]["password"], user.password)]
            if mismatched and not rotate_passwords:
                raise CommandError("Owned fixture passwords differ; explicit rotation is required.")
            for user in mismatched:
                user.set_password(payload[user.role]["password"])
                user.save(update_fields=["password"])
                Token.objects.filter(user=user).delete()
            if not isinstance(child.lorebook_flags, dict):
                raise CommandError("Owned fixture discovery state is invalid.")
            updated_flags = {**child.lorebook_flags, **flags}
            changed_flags = updated_flags != child.lorebook_flags
            if changed_flags:
                child.lorebook_flags = updated_flags
                child.save(update_fields=["lorebook_flags"])
            return _receipt("updated" if mismatched or changed_flags else "verified", family, parent, child)
    except IntegrityError:
        raise CommandError("Live-test provisioning collided; verify ownership and retry.") from None
