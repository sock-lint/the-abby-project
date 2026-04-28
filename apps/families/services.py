"""Services for the Family domain — currently just self-signup orchestration."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    ValidationError as PasswordValidationError,
    validate_password,
)
from django.db import transaction
from rest_framework.authtoken.models import Token

from .models import Family


class FamilyServiceError(ValueError):
    """Raised on validation failure of FamilyService.create_family_with_parent.

    The view layer turns this into a 400. Single ValueError-style error so
    the view doesn't have to discriminate between subtypes.
    """


class FamilyService:
    @staticmethod
    @transaction.atomic
    def create_family_with_parent(
        *,
        username: str,
        password: str,
        display_name: str = "",
        family_name: str,
    ) -> tuple["User", Family, Token]:  # type: ignore[name-defined]
        """Create a Family and its founding parent.

        Returns ``(parent, family, token)``. Raises ``FamilyServiceError`` on
        validation failure (duplicate username, weak password, missing
        family_name). All writes are atomic — a failure mid-flow rolls back
        the partial Family insert.
        """
        User = get_user_model()
        username = (username or "").strip()
        family_name = (family_name or "").strip()
        display_name = (display_name or "").strip() or username

        if not username:
            raise FamilyServiceError("Username is required.")
        if not password:
            raise FamilyServiceError("Password is required.")
        if not family_name:
            raise FamilyServiceError("Family name is required.")
        if len(family_name) > 120:
            raise FamilyServiceError("Family name is too long (max 120 characters).")
        if User.objects.filter(username=username).exists():
            raise FamilyServiceError("Username is already taken.")

        # Run Django's password validators against an in-memory user instance —
        # rejects too-short / too-common / numeric-only / similar-to-username.
        candidate = User(username=username, role="parent")
        try:
            validate_password(password, user=candidate)
        except PasswordValidationError as exc:
            raise FamilyServiceError("; ".join(exc.messages))

        family = Family.objects.create(name=family_name)
        parent = User.objects.create_user(
            username=username,
            password=password,
            display_name=display_name,
            role="parent",
            family=family,
        )
        family.primary_parent = parent
        family.save(update_fields=["primary_parent"])
        token, _ = Token.objects.get_or_create(user=parent)
        return parent, family, token
