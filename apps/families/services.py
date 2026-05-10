"""Services for the Family domain — signup orchestration + member-lifecycle guards."""
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


class MemberRemovalError(FamilyServiceError):
    """Raised when removing/deactivating a member would break family invariants.

    Subclasses ``FamilyServiceError`` so generic catch sites still work; the
    distinct type lets the user-management views surface 400s for member
    removal failures consistently.
    """


def assert_safe_to_remove(user, requesting_user, *, mode: str) -> None:
    """Raise ``MemberRemovalError`` if removing ``user`` is unsafe.

    ``mode`` is either ``"delete"`` or ``"deactivate"`` and is used only
    for error messages — the underlying invariants are the same in both
    modes:

    * Cannot self-target (locks the requester out mid-action).
    * Cannot leave the family with zero active parents.

    Children are never the last-active-anything, so the second guard is a
    no-op for child rows. Parents pay full attention to it.
    """
    if mode not in {"delete", "deactivate"}:
        raise ValueError(f"Unknown removal mode: {mode!r}")

    if user.pk == requesting_user.pk:
        verb = "delete" if mode == "delete" else "deactivate"
        raise MemberRemovalError(f"You cannot {verb} your own account.")

    if user.role == "parent":
        from .queries import parents_in
        siblings = parents_in(user.family).exclude(pk=user.pk)
        if not siblings.exists():
            verb = "removed" if mode == "delete" else "deactivated"
            raise MemberRemovalError(
                f"At least one active parent must remain in the family — "
                f"this parent cannot be {verb}."
            )


def promote_next_primary_parent(family: Family, leaving_user) -> None:
    """If ``leaving_user`` is the family's primary parent, hand the role off.

    Picks the next-oldest active parent (by ``date_joined``) as the new
    primary. ``Family.primary_parent`` has ``on_delete=SET_NULL`` so this
    is mostly cosmetic for the founder pointer — but the founder pointer
    is what the signup flow + family-meta UI surface.
    """
    if family.primary_parent_id != leaving_user.pk:
        return
    from .queries import parents_in
    next_primary = (
        parents_in(family).exclude(pk=leaving_user.pk).order_by("date_joined").first()
    )
    family.primary_parent = next_primary
    family.save(update_fields=["primary_parent"])


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
