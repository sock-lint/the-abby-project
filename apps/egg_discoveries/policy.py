"""Prospective collection policy, separate from ownership and saved promises."""
from collections.abc import Mapping

from django.conf import settings


def discovery_enabled():
    return getattr(settings, "EGG_DISCOVERY_ENABLED", False) is True


def legacy_egg_acquisition_allowed(item):
    """New rolls/offers cannot compete with the selected discovery.

    This must never gate saved inventory, accepted reward delivery or hatch
    ingredients. Detached forecasting records use the same item-type boundary.
    """
    kind = item.get("item_type") if isinstance(item, Mapping) else getattr(item, "item_type", None)
    return not discovery_enabled() or kind != "egg"
