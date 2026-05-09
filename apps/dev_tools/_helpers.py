"""Shared helpers for dev_tools management commands.

Every command takes ``--user <username>`` and gates on ``is_enabled()``.
This module owns those two patterns so each command file stays focused on
its one job.
"""
from __future__ import annotations

from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import CommandError

from apps.dev_tools.gate import assert_enabled


def add_user_arg(parser, *, dest: str = "user", required: bool = True, help_text: str | None = None) -> None:
    """Standard ``--user <username>`` flag.

    Used by every command that targets one user. Prefer ``username`` over a
    raw id since seed-test scenarios ship with stable usernames (``t-fresh``,
    ``t-streak-99`` etc.).
    """
    parser.add_argument(
        f"--{dest.replace('_', '-')}",
        dest=dest,
        required=required,
        help=help_text or "Target username (e.g. 't-streak-99' or 'abby').",
    )


def resolve_user(username: str) -> Any:
    """Load a user by username; raise ``CommandError`` if not found."""
    User = get_user_model()
    try:
        return User.objects.get(username=username)
    except User.DoesNotExist as e:
        raise CommandError(f"No user with username={username!r}") from e


def setup(parser_args, **_unused) -> None:
    """Hook commands can call at the top of ``handle()`` to gate-check."""
    assert_enabled()
