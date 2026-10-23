"""Scoped fresh contexts for the remaining legacy household RPG handlers."""
from contextlib import contextmanager
from functools import wraps

from .context import get_current_user, reset_current_user, set_current_user
from .errors import MCPPermissionDenied
from .retries import authorized_household


def locked_member_ids(*, required=True):
    """Return the exact locked cohort; never adopt a member joining later."""
    selected = getattr(get_current_user(), "_mcp_locked_member_ids", None)
    if selected is None and required:
        raise MCPPermissionDenied("Current household authority is required.")
    return selected


@contextmanager
def household_context(actor, target=None, *, allow_inactive_target=False, family_members=False):
    """Retain current actor/target authority through domain work and serialization."""
    with authorized_household(
        actor, actor if target is None else target,
        allow_inactive_target=allow_inactive_target, lock_family_members=family_members,
    ) as (fresh_actor, fresh_target):
        token = set_current_user(fresh_actor)
        try:
            yield fresh_actor, fresh_target
        finally:
            reset_current_user(token)


def household_operation(*, family_members=False):
    """Guard actor-owned shop rows or entry-ID/multi-child household operations.

    Scalar Coin and skill handlers use actor-plus-target locks through
    household_context. Quest assignment also locks its private author cohort.
    """
    def decorate(function):
        @wraps(function)
        def wrapped(params):
            with household_context(get_current_user(), family_members=family_members):
                return function(params)
        return wrapped
    return decorate
