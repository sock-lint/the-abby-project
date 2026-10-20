"""Conservative item-capacity proofs for the Lab's finite completion sources.

This is structural feasibility, not a probability or a forecast. A source is
added only after its prerequisite proof; proof acquisitions consume its units.
"""
from collections import Counter
from itertools import product
import math
from types import SimpleNamespace

from apps.pets.lifecycle import growth_thresholds
from apps.rpg.item_effects import PREFERRED_FOOD_BONUS, food_base_growth


class ItemCapacity:
    def __init__(self, catalog, renewable=()):
        self.catalog = catalog
        self.renewable = set(renewable)
        self.fixed = Counter()
        self.pools = {}
        self.slots = Counter()
        self.pets = {}
        self.collected = set()

    def clone(self):
        other = ItemCapacity(self.catalog, self.renewable)
        other.fixed = self.fixed.copy()
        other.pools = {key: set(value) for key, value in self.pools.items()}
        other.slots = self.slots.copy()
        other.pets = dict(self.pets)
        other.collected = set(self.collected)
        return other

    def add_draws(self, source, items, quantity=1, *, repeatable=False):
        if repeatable:
            self.renewable.update(items)
        elif items:
            self.pools[source] = set(items)
            self.slots[source] += quantity

    def _choices(self, item_ids):
        if set(item_ids) & self.renewable:
            return [(None, None)]
        result = [("fixed", pk) for pk in item_ids if self.fixed[pk] > 0]
        result.extend(("slot", key) for key, ids in self.pools.items()
                      if self.slots[key] > 0 and set(item_ids) & ids)
        return result

    def _consume(self, choice):
        kind, key = choice
        if kind == "fixed":
            self.fixed[key] -= 1
        elif kind == "slot":
            self.slots[key] -= 1
            if self.slots[key] < 0:
                return False
        return True

    def _food_growth(self, pk, species):
        item = self.catalog.items[pk]
        food_type = str(item.metadata.get("food_type", "")).strip()
        preferred = (item.food_species_id == species.pk if item.food_species_id else
                     bool(food_type) and food_type == species.food_preference)
        return food_base_growth(SimpleNamespace(rarity=item.rarity, metadata=dict(item.metadata))) + (PREFERRED_FOOD_BONUS if preferred else 0)

    def companion_plan(self, pair, growth=0):
        species, potion = self.catalog.pairs[pair]
        existing = self.pets.get(pair)
        eggs = [pk for pk, item in self.catalog.items.items() if item.item_type == "egg" and item.pet_species_id == species.pk]
        potions = [pk for pk, item in self.catalog.items.items() if item.item_type == "potion" and item.potion_type_id == potion.pk]
        choices = [[(None, None)], [(None, None)]] if existing is not None else [self._choices(eggs), self._choices(potions)]
        food = {pk: self._food_growth(pk, species) for pk, item in self.catalog.items.items() if item.item_type == "food"}
        best = None
        for egg, potion_choice in product(*choices):
            candidate = self.clone()
            if not candidate._consume(egg) or not candidate._consume(potion_choice):
                continue
            remaining = max(0, growth - (existing or 0))
            if remaining and not any(pk in self.renewable for pk in food):
                for pk in sorted(food, key=lambda pk: (-food[pk], pk)):
                    units = min(candidate.fixed[pk], math.ceil(remaining / food[pk]))
                    candidate.fixed[pk] -= units
                    remaining = max(0, remaining - units * food[pk])
                pools = sorted(candidate.pools, key=lambda key: -max((food.get(pk, 0) for pk in candidate.pools[key]), default=0))
                for key in pools:
                    points = max((food.get(pk, 0) for pk in candidate.pools[key]), default=0)
                    if not points:
                        continue
                    units = min(candidate.slots[key], math.ceil(remaining / points))
                    candidate.slots[key] -= units
                    remaining = max(0, remaining - units * points)
                if remaining:
                    continue
            candidate.pets[pair] = max(growth, existing or 0)
            cost = (sum(self.slots.values()) - sum(candidate.slots.values()),
                    sum(self.fixed.values()) - sum(candidate.fixed.values()))
            if best is None or cost < best[0]:
                best = cost, candidate
        return best[1] if best else None

    def companion_keys(self, *, feeding):
        keys = set()
        for pair, (species, potion) in self.catalog.pairs.items():
            if self.companion_plan(pair) is None:
                continue
            keys.add(f"pet:{pair}")
            if feeding:
                middle, grown = growth_thresholds(SimpleNamespace(species=species, potion=potion))
                for stage, points in (("middle", middle), ("mount", grown)):
                    if self.companion_plan(pair, points) is not None:
                        keys.add(f"{stage}:{pair}")
        return keys

    def prove_companions(self, count, *, grown=False, distinct_species=False):
        proof = self.clone()
        # This bounded greedy proof may omit an alternative acquisition order;
        # every accepted result nevertheless spends real, distinct units.
        selected = set()
        for pair, points in proof.pets.items():
            species, potion = self.catalog.pairs[pair]
            threshold = growth_thresholds(SimpleNamespace(species=species, potion=potion))[1]
            if not grown or points >= threshold:
                selected.add(pair[0] if distinct_species else pair)
        if len(selected) >= count:
            return proof
        for pair in sorted(self.catalog.pairs):
            identity = pair[0] if distinct_species else pair
            if identity in selected:
                continue
            species, potion = self.catalog.pairs[pair]
            points = growth_thresholds(SimpleNamespace(species=species, potion=potion))[1] if grown else 0
            candidate = proof.companion_plan(pair, points)
            if candidate is not None:
                proof = candidate
                selected.add(identity)
                if len(selected) >= count:
                    return proof
        return None

    def prove_collection(self, item_ids):
        proof = self.clone()
        pending = [pk for pk in set(item_ids) if pk not in proof.collected]
        # Consume the most constrained identities first. There are only the
        # badge and quest completion pools, so this preserves shared slots.
        pending.sort(key=lambda pk: (len(proof._choices([pk])), pk))
        for pk in pending:
            choices = proof._choices([pk])
            if not choices:
                return None
            if not proof._consume(choices[0]):
                return None
            proof.collected.add(pk)
        return proof
