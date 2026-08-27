"""Gate: an ``@action``'s own ``permission_classes`` must never be discarded.

DRF applies ``@action(permission_classes=[...])`` to the view instance through
``initkwargs``, and the default ``get_permissions()`` reads it back off
``self.permission_classes``. A ``get_permissions()`` override that returns a
list unconditionally silently throws it away, so the decorator reads as
protection while doing nothing.

Four endpoints shipped that way:

    ProjectViewSet.activate / approve / request_changes
    HomeworkAssignmentViewSet.save_template

all four gated ``permission_classes=[IsParent]`` and all four reachable by a
child. ``POST /api/projects/<id>/approve/`` returned 200 for the child the
project was assigned to, flipping it to ``completed`` and firing the
``project_bonus`` / ``bounty_payout`` write in ``apps/projects/signals.py`` —
a child paying themselves.

Fixing the four call sites fixes four instances. This test fixes the shape: it
walks every registered viewset in the project, finds the actions that declare
their own permissions, and asserts the view actually returns them. A viewset
added next year is covered without anybody remembering this file exists.
"""
from __future__ import annotations

from django.test import SimpleTestCase
from rest_framework.viewsets import ViewSetMixin


def _iter_viewsets():
    """Every DRF viewset reachable from the root URLconf."""
    from django.urls import get_resolver

    seen = set()

    def walk(patterns):
        for pattern in patterns:
            nested = getattr(pattern, "url_patterns", None)
            if nested is not None:
                yield from walk(nested)
                continue
            callback = getattr(pattern, "callback", None)
            cls = getattr(callback, "cls", None)
            if cls is None or cls in seen:
                continue
            if isinstance(cls, type) and issubclass(cls, ViewSetMixin):
                seen.add(cls)
                yield cls

    yield from walk(get_resolver().url_patterns)


def _declared_permission_actions(viewset_class):
    """(name, permission_classes) for each @action declaring its own gate."""
    for name in dir(viewset_class):
        if name.startswith("_"):
            continue
        handler = getattr(viewset_class, name, None)
        declared = getattr(handler, "kwargs", None)
        if not isinstance(declared, dict):
            continue
        permission_classes = declared.get("permission_classes")
        if permission_classes:
            yield name, tuple(permission_classes)


class ActionPermissionsAreHonouredTests(SimpleTestCase):
    def test_every_action_declared_permission_survives_get_permissions(self):
        offenders = []
        checked = 0

        for viewset_class in _iter_viewsets():
            for action_name, declared in _declared_permission_actions(viewset_class):
                checked += 1
                view = viewset_class()
                view.action = action_name
                # Mirror what DRF's initkwargs do for an @action route.
                view.permission_classes = list(declared)
                effective = {type(p) for p in view.get_permissions()}
                missing = [c.__name__ for c in declared if c not in effective]
                if missing:
                    offenders.append(
                        f"{viewset_class.__module__}.{viewset_class.__name__}"
                        f".{action_name} declares {missing} but get_permissions() "
                        f"returned {sorted(c.__name__ for c in effective)}",
                    )

        self.assertGreater(
            checked, 0,
            "found no @action declaring permission_classes — the walker is "
            "broken, not the codebase",
        )
        self.assertEqual(
            offenders, [],
            "These @action permission_classes are silently discarded by a "
            "get_permissions() override, so the decorator is doing nothing. "
            "Call config.viewsets.action_declares_permissions(self) at the top "
            "of the override and defer to super().get_permissions() when it is "
            "True:\n  " + "\n  ".join(offenders),
        )
