"""Run with `manage.py shell < this_file` on a fresh isolated staging DB.

Passwords arrive through stdin's process environment, never command arguments.
This intentionally refuses repeat execution or a populated database.
"""
import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from apps.families.services import FamilyService


def provision():
    database = settings.DATABASES["default"]
    if (
        os.environ.get("ABBY_STAGING") != "true"
        or database.get("NAME") != "abby_staging"
        or database.get("USER") != "abby_staging"
        or database.get("HOST") != "db"
        or settings.DEBUG
        or settings.ALLOW_PARENT_SIGNUP
        or settings.EMAIL_BACKEND != "django.core.mail.backends.dummy.EmailBackend"
        or settings.USE_S3_STORAGE
    ):
        raise RuntimeError("Refusing to provision outside the isolated staging recipe")
    users = get_user_model()
    passwords = {
        name: os.environ.get(f"ABBY_STAGING_{name.upper()}_PASSWORD", "")
        for name in ("parent", "child", "other_parent", "other_child")
    }
    for name, password in passwords.items():
        if len(password) < 24:
            raise RuntimeError(f"Set a unique random staging password for {name}")
        validate_password(password)
    if len(set(passwords.values())) != len(passwords):
        raise RuntimeError("Each staging identity needs its own password")
    with transaction.atomic():
        if users.objects.exists():
            raise RuntimeError("Refusing to change a populated staging database")
        for prefix, label in (("", "Avatar Test Family"), ("other_", "Isolation Test Family")):
            parent_name = f"{prefix}parent"
            parent, family, token = FamilyService.create_family_with_parent(
                username=f"stage-{parent_name.replace('_', '-')}",
                password=passwords[parent_name], display_name=parent_name.replace("_", " ").title(),
                family_name=label,
            )
            # Login must obtain its own credential; this script never emits one.
            token.delete()
            child_name = f"{prefix}child"
            users.objects.create_user(
                username=f"stage-{child_name.replace('_', '-')}", password=passwords[child_name],
                display_name=child_name.replace("_", " ").title(), role="child", family=family,
            )
    print("Created four synthetic staging identities in two isolated families; no credentials printed.")


provision()
