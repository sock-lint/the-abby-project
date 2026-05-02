"""Shared test helpers for the kinds of mocking many test files repeat.

Use these instead of duplicating patch decorators per file.
"""
from __future__ import annotations

import contextlib
import functools
from unittest.mock import patch


@contextlib.contextmanager
def suppress_drops():
    """Force ``DropService.process_drops`` to never roll a drop.

    Drop rolls inside the RPG game loop fire ``random.random()`` to decide
    whether to grant an item. Any test that asserts on coin / XP / activity
    totals downstream of a triggered game-loop call wants to suppress the
    randomness so the assertion is deterministic. The previous pattern was a
    per-test ``@patch("apps.rpg.services.random.random", return_value=1.0)``;
    this context manager makes it one line and keeps the patch path in one
    place so a future relocation doesn't fan out across 13+ test files.

    Usage::

        with suppress_drops():
            GameLoopService.on_task_completed(child, TriggerType.CHORE_COMPLETE, {})
    """
    with patch("apps.rpg.services.random.random", return_value=1.0):
        yield


def suppress_drops_decorator(func):
    """Decorator form of :func:`suppress_drops` for class-based test methods.

    Equivalent to wrapping the body in a ``suppress_drops()`` block; unlike
    a raw ``@patch(..., return_value=1.0)`` this doesn't add a swallowed
    ``_mock`` positional to the test signature.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with suppress_drops():
            return func(*args, **kwargs)

    return wrapper
