# RPG Phase 2: Drops & Inventory — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the drops/loot system and inventory — items drop on task completion, accumulate in a user inventory, and can be viewed on a new inventory page.

**Architecture:** New models in `apps/rpg/` (ItemDefinition, UserInventory, DropTable, DropLog). New DropService integrates into existing GameLoopService. Frontend gets an inventory page and drop notifications on the dashboard.

**Tech Stack:** Django 5.1, DRF 3.15, React 19, Tailwind 4, Framer Motion, lucide-react

---

## File Structure

### New files:
- `apps/rpg/tests/test_drops.py` — Drop service tests
- `frontend/src/pages/Inventory.jsx` — Inventory page

### Modified files:
- `apps/rpg/models.py` — Add ItemDefinition, UserInventory, DropTable, DropLog
- `apps/rpg/services.py` — Add DropService, hook into GameLoopService
- `apps/rpg/serializers.py` — Add item/inventory serializers
- `apps/rpg/views.py` — Add InventoryViewSet
- `apps/rpg/urls.py` — Register inventory routes
- `apps/rpg/admin.py` — Register new models
- `apps/rpg/tasks.py` — (no changes needed for Phase 2)
- `apps/projects/management/commands/seed_data.py` — Seed item catalog
- `frontend/src/api/index.js` — Add inventory endpoints
- `frontend/src/App.jsx` — Add inventory route
- `frontend/src/components/Layout.jsx` — Add inventory nav item
- `frontend/src/pages/Dashboard.jsx` — Add recent drops widget

---

## Task 1: ItemDefinition and DropTable models

Add to `apps/rpg/models.py`:

```python
class ItemDefinition(TimestampedModel):
    class ItemType(models.TextChoices):
        EGG = "egg", "Pet Egg"
        POTION = "potion", "Hatching Potion"
        FOOD = "food", "Pet Food"
        COSMETIC_FRAME = "cosmetic_frame", "Avatar Frame"
        COSMETIC_TITLE = "cosmetic_title", "Title"
        COSMETIC_THEME = "cosmetic_theme", "Dashboard Theme"
        COSMETIC_PET_ACCESSORY = "cosmetic_pet_accessory", "Pet Accessory"
        QUEST_SCROLL = "quest_scroll", "Quest Scroll"
        COIN_POUCH = "coin_pouch", "Coin Pouch"

    class Rarity(models.TextChoices):
        COMMON = "common", "Common"
        UNCOMMON = "uncommon", "Uncommon"
        RARE = "rare", "Rare"
        EPIC = "epic", "Epic"
        LEGENDARY = "legendary", "Legendary"

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50)
    item_type = models.CharField(max_length=30, choices=ItemType.choices)
    rarity = models.CharField(max_length=20, choices=Rarity.choices, default=Rarity.COMMON)
    coin_value = models.PositiveIntegerField(default=0)  # salvage value
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["item_type", "rarity", "name"]

    def __str__(self):
        return f"{self.icon} {self.name} ({self.get_rarity_display()})"


class UserInventory(TimestampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="inventory")
    item = models.ForeignKey(ItemDefinition, on_delete=models.CASCADE, related_name="inventory_entries")
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        unique_together = ("user", "item")
        ordering = ["item__item_type", "item__name"]

    def __str__(self):
        return f"{self.user} x{self.quantity} {self.item.name}"


class DropTable(TimestampedModel):
    class TriggerType(models.TextChoices):
        CLOCK_OUT = "clock_out", "Clock Out"
        CHORE_COMPLETE = "chore_complete", "Chore Complete"
        HOMEWORK_COMPLETE = "homework_complete", "Homework Complete"
        MILESTONE_COMPLETE = "milestone_complete", "Milestone Complete"
        BADGE_EARNED = "badge_earned", "Badge Earned"
        QUEST_COMPLETE = "quest_complete", "Quest Complete"
        PERFECT_DAY = "perfect_day", "Perfect Day"
        HABIT_LOG = "habit_log", "Habit Log"

    trigger_type = models.CharField(max_length=30, choices=TriggerType.choices)
    item = models.ForeignKey(ItemDefinition, on_delete=models.CASCADE, related_name="drop_table_entries")
    weight = models.PositiveIntegerField(default=1)
    min_level = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["trigger_type", "-weight"]

    def __str__(self):
        return f"{self.get_trigger_type_display()} → {self.item.name} (w={self.weight})"


class DropLog(CreatedAtModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="drop_logs")
    item = models.ForeignKey(ItemDefinition, on_delete=models.CASCADE, related_name="drop_log_entries")
    trigger_type = models.CharField(max_length=30)
    quantity = models.PositiveIntegerField(default=1)
    was_salvaged = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
```

Tests, admin registration, migration. Commit separately.

## Task 2: DropService

Add `DropService` to `apps/rpg/services.py`:

**Constants:**
```python
BASE_DROP_RATES = {
    "clock_out": 0.40,
    "chore_complete": 0.30,
    "homework_complete": 0.35,
    "milestone_complete": 0.80,
    "badge_earned": 1.00,
    "quest_complete": 1.00,
    "perfect_day": 1.00,
    "habit_log": 0.15,
}
STREAK_DROP_BONUS_PER_DAY = 0.05
STREAK_DROP_BONUS_CAP = 0.50
```

**`DropService.process_drops(user, trigger_type, streak_bonus=0)`:**
1. Calculate effective drop rate = BASE_DROP_RATES.get(trigger_type, 0.2) + streak_bonus
2. Roll random(); if > effective rate, return empty list
3. Get user level from CharacterProfile
4. Filter DropTable by trigger_type and min_level <= user level
5. If no entries, return empty
6. Weighted random select from matching entries
7. Check if item is cosmetic and user already owns it → set was_salvaged=True, award coin_value
8. Otherwise → increment UserInventory (get_or_create, increment quantity)
9. Create DropLog entry
10. Return list of dicts: [{item_id, item_name, item_icon, item_rarity, quantity, was_salvaged}]

**`DropService.get_inventory(user)`:**
- Return UserInventory entries with select_related("item"), grouped by item_type

Tests covering: drop when roll succeeds, no drop when roll fails, weighted selection, salvage logic, inventory increment, min_level filtering.

## Task 3: Hook drops into GameLoopService

Modify `GameLoopService.on_task_completed` to call `DropService.process_drops` after streak update.

Calculate streak_bonus from profile: `min(profile.login_streak * STREAK_DROP_BONUS_PER_DAY, STREAK_DROP_BONUS_CAP)`

Add drops to the return dict.

## Task 4: Inventory serializers, views, URLs

- ItemDefinitionSerializer (read-only)
- UserInventorySerializer (nested item)
- InventoryView (GET /api/inventory/) — returns grouped inventory
- RecentDropsView (GET /api/drops/recent/) — returns last 10 drops
- Register in urls.py and config/urls.py (already registered)

## Task 5: Seed item catalog

Add `_create_item_catalog` to seed_data.py with initial items:
- 8 pet eggs (one per species: Wolf, Dragon, Fox, Owl, Cat, Bear, Phoenix, Unicorn)
- 6 hatching potions (Base, Fire, Ice, Shadow, Golden, Cosmic)
- 6 pet foods (Meat, Fish, Berries, Seeds, Honey, Cake)
- 3 coin pouches (Small 5, Medium 15, Large 50)
- Drop table entries linking items to triggers with appropriate weights

## Task 6: Frontend inventory page + dashboard drops widget

- Create `frontend/src/pages/Inventory.jsx`
- Add API functions: getInventory, getRecentDrops
- Add route and nav item
- Add recent drops ticker to Dashboard

---

## Verification

1. Django check passes
2. Frontend build succeeds
3. Seed data creates item catalog
4. Game loop triggers drops on task completion
5. Inventory page displays items grouped by type
6. Dashboard shows recent drops
