# RPG Gamification Layer — Design Spec

**Date:** 2026-04-13
**Status:** Approved
**Approach:** Hybrid A+B architecture

## Context

The Abby Project has solid productivity mechanics (projects, timecards, chores, homework, achievements) but lacks the daily engagement hooks and "game feel" that make kids want to come back every day. Inspired by Habitica's RPG gamification, this spec adds a full RPG layer: character progression, daily engagement systems, a drops/loot economy, a collectible pet-to-mount creature system, a quest/boss-fight system, habits, and cosmetics. The goal is to increase daily engagement, add fun and delight, and create gentle nudges for consistency — all without punitive mechanics.

## Architecture

Three new Django apps in a hybrid layout:

- **`apps/rpg/`** — Character profile, streaks, daily engagement, drops/loot, inventory, cosmetics, habits, and the central game loop orchestrator.
- **`apps/pets/`** — Creature lifecycle: species, eggs, hatching potions, food, pets, mounts, stable UI.
- **`apps/quests/`** — Quest definitions, boss fights, collection quests, progress tracking, rewards, system linkages.

All three hook into existing signals via `apps/rpg/services/game_loop.py`, the single entry point that orchestrates streak updates, drop rolls, quest progress, and pet checks on every qualifying action.

---

## Section 1: Character Profile & Daily Engagement

### Character Profile

Extends `User` via a new `CharacterProfile` model (one-to-one):

| Field | Type | Description |
|-------|------|-------------|
| `user` | OneToOneField(User) | Link to existing user |
| `level` | IntegerField | Computed from total XP across all skills |
| `title` | ForeignKey(ItemDefinition, null) | Currently equipped title |
| `active_frame` | ForeignKey(ItemDefinition, null) | Currently equipped avatar frame |
| `login_streak` | IntegerField | Consecutive days with at least one task completed |
| `longest_login_streak` | IntegerField | All-time record |
| `last_active_date` | DateField | Last day any task was completed |
| `perfect_days_count` | IntegerField | Lifetime count of perfect days |

**Level computation:** Sum all `SkillProgress.xp` for the user into `total_xp`. Apply the same thresholds as individual skills (L1=100, L2=300, L3=600, L4=1000, L5=1500, L6=2500) but scaled 10x for global level (L1=1000, L2=3000, etc.) to account for XP accumulating across many skills. `CharacterProfile.level` is recomputed and saved on each XP change (not a `@property`) for query performance. Display prominently on dashboard and profile.

**Titles:** Unlocked at level milestones. Stored as `ItemDefinition` with `item_type=title`. Auto-granted titles:
- L1: "Novice Maker"
- L5: "Apprentice Crafter"
- L10: "Journeyman Builder"
- L20: "Master Artisan"
- L30: "Legendary Forgemaster"

Additional titles earnable through quests, badges, or purchase.

### Daily Engagement

**Login streak:** Tracked by `last_active_date`. If today minus last_active_date > 1 day, streak resets to 0. Any task completion updates `last_active_date` to today and increments streak if needed.

**Daily check-in bonus:** First qualifying action each day awards:
- Base: 3 coins + small XP
- Streak multiplier: `min(1 + (login_streak * 0.07), 2.0)` — caps at 2x after ~14 days
- Bonus drop chance: +5% per streak day, capped at +50%

**Perfect Day:** Evaluated by nightly Celery task. A day is "perfect" if ALL of:
- Every active daily chore was completed
- Every homework assignment due that day was submitted
- At least one project clock-in occurred (if any project is active)

Perfect Day rewards:
- Bonus coins (15)
- Guaranteed uncommon+ drop
- Streak flame goes golden for the next day
- Increments `perfect_days_count`

**Gentle nudges for missed days:**
- Streak flame visual dims (goes grey)
- Active pet gets a "sleepy" overlay on dashboard
- Streak multiplier resets to 1.0
- No coin loss, no XP loss, no level regression

---

## Section 2: Drops & Loot System

### Core Mechanics

Every qualifying action (clock-out, chore approved, homework approved, milestone completed, badge earned) triggers a drop roll. The roll checks a configurable drop table and may award items to the user's inventory.

### Drop Categories

| Category | Examples | Purpose |
|----------|----------|---------|
| Pet Eggs | Wolf Egg, Dragon Egg | Hatch into pets |
| Hatching Potions | Fire Potion, Ice Potion | Combine with eggs for variants |
| Pet Food | Meat, Fish, Berries, Cake | Feed pets to grow toward mount |
| Cosmetic Items | Avatar frames, pet accessories | Visual customization |
| Quest Scrolls | Boss scroll, Collection scroll | Start a quest |
| Coin Pouches | Small (5), Medium (15), Large (50) | Bonus coins |

### Drop Table Mechanics

- Each trigger type has a base drop rate (e.g., clock-out: 40%, chore: 30%, milestone: 80%, badge: 100%)
- Within a drop, rarity weights determine what tier: Common 60%, Uncommon 25%, Rare 10%, Epic 4%, Legendary 1%
- Login streak adds +5% to base drop rate per day (capped at +50%)
- Perfect Day grants a guaranteed uncommon+ drop
- Already-owned cosmetics auto-salvage into coins

### Models (`apps/rpg/`)

```python
class ItemDefinition(TimestampedModel):
    name = CharField(max_length=100)
    description = TextField(blank=True)
    icon = CharField(max_length=50)  # emoji or icon key
    item_type = CharField(choices=[
        'egg', 'potion', 'food', 'cosmetic_frame', 'cosmetic_title',
        'cosmetic_theme', 'cosmetic_pet_accessory', 'quest_scroll', 'coin_pouch'
    ])
    rarity = CharField(choices=['common', 'uncommon', 'rare', 'epic', 'legendary'])
    coin_value = IntegerField(default=0)  # salvage value
    metadata = JSONField(default=dict)  # type-specific data (e.g., potion color, food nutrition)

class UserInventory(TimestampedModel):
    user = ForeignKey(User)
    item = ForeignKey(ItemDefinition)
    quantity = PositiveIntegerField(default=1)
    class Meta:
        unique_together = ('user', 'item')

class DropTable(TimestampedModel):
    trigger_type = CharField(choices=[
        'clock_out', 'chore_complete', 'homework_complete',
        'milestone_complete', 'badge_earned', 'quest_complete',
        'perfect_day'
    ])
    item = ForeignKey(ItemDefinition)
    weight = PositiveIntegerField(default=1)  # relative probability within this trigger
    min_level = IntegerField(default=0)  # player must be at least this level

class DropLog(CreatedAtModel):
    user = ForeignKey(User)
    item = ForeignKey(ItemDefinition)
    trigger_type = CharField(max_length=30)
    quantity = PositiveIntegerField(default=1)
```

### Service: `apps/rpg/services/drops.py`

```
process_drops(user, trigger_type, streak_bonus=0) -> list[DropResult]
```
1. Calculate effective drop rate = base_rate[trigger_type] + streak_bonus
2. Roll RNG; if no drop, return empty
3. Filter `DropTable` rows by trigger_type and user level
4. Weighted random select from matching rows
5. If cosmetic and already owned → salvage to coins
6. Otherwise → increment `UserInventory`
7. Log to `DropLog`
8. Return list of `DropResult(item, quantity, was_salvaged)`

---

## Section 3: Pets & Creatures

### Lifecycle: Egg → Pet → Mount

1. **Hatching:** Player selects one Egg + one Hatching Potion from inventory → creates a `UserPet`. The potion determines the variant (color/element). Both items are consumed.
2. **Feeding:** Pets have a growth meter (0–100). Feeding a `Food` item from inventory adds growth points. Preferred food gives +15 points; neutral food gives +5. At 100 growth, the pet auto-evolves.
3. **Evolution:** At 100 growth, the pet becomes a `UserMount`. The pet entry is marked `evolved_to_mount=True` and remains in the stable as a "raised" pet. The mount is a separate collectible.

### Species & Variants

Start with 8 base species and 6 potion variants = 48 pet/mount combinations.

**Base species:**
| Species | Icon | Food Preference |
|---------|------|----------------|
| Wolf | 🐺 | Meat |
| Dragon | 🐉 | Fish |
| Fox | 🦊 | Berries |
| Owl | 🦉 | Seeds |
| Cat | 🐱 | Fish |
| Bear | 🐻 | Honey |
| Phoenix | 🔥 | Cake |
| Unicorn | 🦄 | Candy |

**Potion variants:**
| Potion | Visual | Rarity |
|--------|--------|--------|
| Base | Natural colors | Common |
| Fire | Red/orange tones | Uncommon |
| Ice | Blue/white tones | Uncommon |
| Shadow | Dark/purple tones | Rare |
| Golden | Gold/glowing | Epic |
| Cosmic | Starfield/nebula | Legendary |

### Models (`apps/pets/`)

```python
class PetSpecies(TimestampedModel):
    name = CharField(max_length=50)
    icon = CharField(max_length=10)  # emoji
    description = TextField(blank=True)
    food_preference = CharField(max_length=30)  # matches Food.food_type

class PotionType(TimestampedModel):
    name = CharField(max_length=50)
    color_hex = CharField(max_length=7)
    rarity = CharField(choices=RARITY_CHOICES)
    description = TextField(blank=True)

class UserPet(TimestampedModel):
    user = ForeignKey(User)
    species = ForeignKey(PetSpecies)
    potion = ForeignKey(PotionType)
    growth_points = PositiveIntegerField(default=0)  # 0–100
    is_active = BooleanField(default=False)
    evolved_to_mount = BooleanField(default=False)
    class Meta:
        unique_together = ('user', 'species', 'potion')

class UserMount(TimestampedModel):
    user = ForeignKey(User)
    species = ForeignKey(PetSpecies)
    potion = ForeignKey(PotionType)
    is_active = BooleanField(default=False)
    class Meta:
        unique_together = ('user', 'species', 'potion')
```

### Service: `apps/pets/services.py`

- `hatch_pet(user, egg_item_id, potion_item_id)` — validate inventory, consume items, create `UserPet`
- `feed_pet(user, pet_id, food_item_id)` — apply growth points, check evolution threshold
- `set_active_pet(user, pet_id)` — deactivate current, activate new
- `set_active_mount(user, mount_id)` — deactivate current, activate new
- `get_stable(user)` — return all pets/mounts grouped by species, with silhouettes for uncollected

### Gentle Nudges

- **Sleepy pet:** If child has an active pet and `last_active_date < today`, the pet's display gets a "💤" overlay. No growth decay.
- **Happy pet:** Completing a task while a pet is active shows a brief "pet happy" animation/notification.
- **No pet death/starvation:** Pets never lose growth or disappear. Worst case is cosmetic sleepy state.

### Display

- **Stable page** (`/pets`): Grid of all 48 possible pets. Owned = full color with growth bar. Unowned = grey silhouette. Same for mounts tab.
- **Dashboard widget:** Active pet with name, species, variant, growth bar. Active mount displayed beside avatar.
- **Collection stats:** "Pets: 12/48 | Mounts: 5/48"

---

## Section 4: Quest System

### Quest Types

**Boss Fights:**
- Boss has an HP pool. Tasks completed during the quest deal damage.
- Damage formula per trigger:
  - Clock-out: 10 damage per hour
  - Chore complete: 15 damage
  - Homework complete: 25 damage (scaled by effort level)
  - Milestone complete: 50 damage
  - Habit logged: 5 damage
- Time limit (configurable, typically 7 days). If boss isn't defeated, quest expires — no rewards, no penalty.
- **Rage (gentle):** If a full day passes with zero tasks from any participant, boss gains a 20-point shield (i.e., `current_progress` is reduced by 20, min 0). Creates visual urgency ("The boss fought back!") but is easily recoverable with normal activity.

**Collection Quests:**
- Goal: collect N items through random drops during the quest period.
- Each qualifying task has a chance to drop the quest-specific collectible.
- Typically shorter/easier than boss fights. Good for solo play.

### Quest Lifecycle

1. Player uses a Quest Scroll from inventory (or parent assigns/creates a quest)
2. Quest becomes active — visible on dashboard with progress bar
3. Tasks completed during the quest contribute to progress (filtered by `trigger_filter`)
4. Quest completes (success) or expires (time limit)
5. **One active quest at a time** per user

### System Linkages

Quests can be linked to other elements via `QuestDefinition` fields and `trigger_filter`:

| Linkage | Field | Example |
|---------|-------|---------|
| Project-scoped | `trigger_filter.project_id` | "Only woodworking project hours count" |
| Skill-scoped | `trigger_filter.skill_category_id` | "Only Coding skill XP actions count" |
| Chore-scoped | `trigger_filter.chore_ids` | "Only these specific chores count" |
| Homework-scoped | `trigger_filter.homework_ids` | "Only homework submissions count" |
| Badge-gated | `required_badge` FK | "Must have 'Week Warrior' badge to start" |
| Savings-linked | `trigger_filter.savings_goal_id` | "Each dollar saved = 1 boss damage" |
| Streak-based | `trigger_filter.streak_target` | "Maintain a 14-day streak to complete" |
| Perfect-day-based | `trigger_filter.perfect_day_target` | "Achieve 5 perfect days to win" |

**`trigger_filter` JSONField shape:**
```json
{
  "allowed_triggers": ["clock_out", "milestone_complete", "chore_complete",
                        "homework_complete", "savings_credit", "streak_check",
                        "perfect_day", "habit_log"],
  "project_id": null,
  "skill_category_id": null,
  "chore_ids": null,
  "homework_ids": null,
  "savings_goal_id": null,
  "streak_target": null,
  "perfect_day_target": null
}
```

An empty/null filter means all triggers count (default behavior).

### Multi-player (Future-Ready)

- `Quest.party` FK (nullable) — solo quests leave it null
- `QuestParticipant` tracks per-user contributions
- Boss HP and collection targets scale with party size (e.g., `base_hp * (1 + 0.5 * (party_size - 1))`)
- All party members receive the same rewards on completion
- Party/scaling logic exists in the model but is not exposed in the UI until multi-family support is built

### Models (`apps/quests/`)

```python
class QuestDefinition(TimestampedModel):
    name = CharField(max_length=100)
    description = TextField()
    icon = CharField(max_length=50)
    quest_type = CharField(choices=['boss', 'collection'])
    target_value = PositiveIntegerField()  # HP for boss, count for collection
    duration_days = PositiveIntegerField(default=7)
    trigger_filter = JSONField(default=dict)
    required_badge = ForeignKey('achievements.Badge', null=True, blank=True)
    coin_reward = PositiveIntegerField(default=0)
    xp_reward = PositiveIntegerField(default=0)
    is_repeatable = BooleanField(default=False)
    is_system = BooleanField(default=False)  # system-curated vs parent-created
    created_by = ForeignKey(User, null=True)  # null for system quests

class QuestRewardItem(TimestampedModel):
    quest_definition = ForeignKey(QuestDefinition)
    item = ForeignKey('rpg.ItemDefinition')
    quantity = PositiveIntegerField(default=1)

class Quest(TimestampedModel):
    definition = ForeignKey(QuestDefinition)
    status = CharField(choices=['active', 'completed', 'failed', 'expired'])
    start_date = DateTimeField()
    end_date = DateTimeField()
    current_progress = PositiveIntegerField(default=0)
    party = ForeignKey('Party', null=True, blank=True)  # future

class QuestParticipant(TimestampedModel):
    quest = ForeignKey(Quest)
    user = ForeignKey(User)
    contribution = PositiveIntegerField(default=0)  # damage dealt or items collected
```

### Parent Controls

- Parents can create custom quests via Manage page: set name, type, target, duration, trigger filters, and rewards
- System offers a rotating pool of weekly curated quests (seeded by `seed_data`)
- Parents can assign quest scrolls directly to a child (bypasses inventory)

---

## Section 5: Cosmetics & Habits

### Cosmetics System

All cosmetics are `ItemDefinition` entries with specific `item_type` values. Equipping stores the FK on `CharacterProfile`.

| Cosmetic Slot | Profile Field | Source |
|--------------|---------------|--------|
| Avatar Frame | `active_frame` | Drops, quest rewards, shop purchase |
| Title | `active_title` | Level milestones (auto), drops, quests |
| Dashboard Theme | `active_theme` | Drops, quest rewards (extends existing theme system) |
| Pet Accessory | `active_pet_accessory` | Drops, quest rewards |

Cosmetics can also be listed in the existing Reward shop for coin purchase, bridging the existing economy with the new system.

### Habits (New Task Type)

Micro-behaviors tracked with +/- buttons, distinct from chores (which are recurring daily/weekly tasks with approval flow).

**Key differences from chores:**
- No parent approval needed — self-reported
- Can be tapped multiple times per day
- No monetary reward — only coins, XP, and drop chances
- Track "strength" (frequency) rather than completion status

```python
class Habit(TimestampedModel):
    name = CharField(max_length=100)
    icon = CharField(max_length=10)
    habit_type = CharField(choices=['positive', 'negative', 'both'])
    user = ForeignKey(User)  # the child this habit is for
    created_by = ForeignKey(User)  # parent or child
    coin_reward = PositiveIntegerField(default=1)  # per positive tap
    xp_reward = PositiveIntegerField(default=5)  # per positive tap
    strength = IntegerField(default=0)  # positive = frequently done, negative = frequently lapsed
    is_active = BooleanField(default=True)

class HabitLog(CreatedAtModel):
    habit = ForeignKey(Habit)
    user = ForeignKey(User)
    direction = SmallIntegerField()  # +1 or -1
    streak_at_time = IntegerField(default=0)
```

**Strength mechanic:** Each positive tap adds +1 to strength. Each negative tap subtracts 1. Strength decays by 1 daily (via nightly Celery task) if no positive tap occurred that day. Strength determines color:
- < -5: Dark red
- -5 to -1: Light red
- 0: Yellow (neutral)
- 1 to 5: Light green
- 5 to 10: Green
- > 10: Deep blue

**Gentle nudges for negative habits:** Logging a negative habit dims the streak flame slightly and makes the active pet look "concerned". No coin or XP loss.

### Frontend Pages

- `/pets` — Stable page (pet grid, mount grid, active pet management, hatching UI, feeding UI)
- `/quests` — Active quest dashboard, available quest scrolls, quest history
- Existing `/rewards` — Extended with cosmetic items section
- Existing dashboard — Widgets for active pet, quest progress, streak flame, daily check-in, recent drops

---

## Section 6: Integration & Game Loop

### Central Orchestrator: `apps/rpg/services/game_loop.py`

```python
def on_task_completed(user, trigger_type, context=None):
    """
    Single entry point called from all existing signals.
    Orchestrates the full game loop for each qualifying action.

    Args:
        user: The child user who completed the action
        trigger_type: str — 'clock_out', 'chore_complete', etc.
        context: dict — optional metadata (project_id, skill_category_id, etc.)

    Returns:
        GameEvent with: streak_update, drops, quest_progress, pet_reaction, notifications
    """
```

**Execution order:**
1. **Streak update** — check if this is first action today, update login_streak
2. **Daily check-in bonus** — if first action today, award streak-scaled coins/XP
3. **Drop roll** — call `process_drops(user, trigger_type, streak_bonus)`
4. **Quest progress** — if active quest, evaluate trigger against filter, update progress
5. **Pet reaction** — if active pet, generate happy/growth notification
6. **Perfect Day check** — (deferred to nightly task, but flag if all dailies done so far)
7. **Bundle notifications** — combine all events into a single rich notification

### Signal Integration Points

Existing signals that call `on_task_completed`:

| Signal Location | Trigger Type | Context |
|----------------|-------------|---------|
| `apps/timecards/services.py` (clock-out) | `clock_out` | `{hours, project_id, skill_tags}` |
| `apps/chores/services.py` (approve) | `chore_complete` | `{chore_id}` |
| `apps/homework/services.py` (approve) | `homework_complete` | `{homework_id, effort_level}` |
| `apps/projects/signals.py` (milestone) | `milestone_complete` | `{project_id, milestone_id}` |
| `apps/achievements/services.py` (badge) | `badge_earned` | `{badge_id, rarity}` |
| `apps/projects/signals.py` (project done) | `project_complete` | `{project_id, payment_kind}` |
| `apps/rpg/views.py` (habit tap) | `habit_log` | `{habit_id, direction}` |

### Celery Tasks

| Task | Schedule | Purpose |
|------|----------|---------|
| `evaluate_perfect_day` | Daily 23:55 local | Check all children for perfect day, award bonuses |
| `decay_habit_strength` | Daily 00:05 local | Reduce strength by 1 for habits not tapped today |
| `expire_quests` | Daily 00:10 local | Mark expired quests as failed |
| `weekly_quest_rotation` | Sunday 00:00 local | Refresh system quest pool |

### API Endpoints (New)

**`apps/rpg/` routes:**
- `GET /api/character/` — profile, level, streak, title, frame
- `GET /api/inventory/` — all items grouped by type
- `POST /api/inventory/use/` — use an item (hatch egg, start quest scroll)
- `GET /api/drops/recent/` — last N drops for the feed
- `GET /api/streaks/` — current streak, longest streak, perfect day count
- `GET /api/habits/` — list habits
- `POST /api/habits/` — create habit
- `POST /api/habits/{id}/log/` — record +/- tap
- `GET /api/cosmetics/` — available cosmetics
- `POST /api/character/equip/` — equip frame/title/theme/pet accessory

**`apps/pets/` routes:**
- `GET /api/pets/stable/` — full collection grid (owned + silhouettes)
- `POST /api/pets/hatch/` — hatch egg + potion
- `POST /api/pets/{id}/feed/` — feed food item
- `POST /api/pets/{id}/activate/` — set as active pet
- `GET /api/mounts/` — mount collection
- `POST /api/mounts/{id}/activate/` — set as active mount

**`apps/quests/` routes:**
- `GET /api/quests/active/` — current active quest with progress
- `GET /api/quests/available/` — quest scrolls in inventory + system rotation
- `POST /api/quests/start/` — start a quest from scroll
- `GET /api/quests/history/` — completed/failed quests
- `POST /api/quests/` — (parent) create custom quest
- `POST /api/quests/{id}/assign/` — (parent) assign quest to child

---

## Phasing

### Phase 1: Foundation (Character + Streaks + Habits)
- `CharacterProfile` model + migration
- Login streak tracking + daily check-in bonus
- Perfect Day evaluation (Celery task)
- Habit model + CRUD + logging
- Dashboard widgets (streak flame, level display)
- Game loop service skeleton (streak + habit triggers only)

### Phase 2: Drops & Inventory
- `ItemDefinition`, `UserInventory`, `DropTable`, `DropLog` models
- Drop service with configurable tables
- Seed initial item catalog (eggs, potions, food, coin pouches)
- Inventory page (frontend)
- Hook drops into game loop (all trigger types)
- Recent drops feed on dashboard

### Phase 3: Pets & Creatures
- `PetSpecies`, `PotionType`, `UserPet`, `UserMount` models
- Hatching, feeding, evolution services
- Stable page (frontend) with collection grid
- Active pet/mount display on dashboard
- Sleepy/happy pet reactions
- Seed 8 species + 6 potions

### Phase 4: Quests & Boss Fights
- `QuestDefinition`, `Quest`, `QuestParticipant`, `QuestRewardItem` models
- Quest lifecycle service (start, progress, complete, expire)
- Trigger filter evaluation
- System quest rotation (Celery task)
- Quest page (frontend) with boss HP bar / collection progress
- Parent quest creation UI in Manage page
- All system linkages (project, skill, savings, streak, etc.)

### Phase 5: Cosmetics & Polish
- Cosmetic item definitions (frames, themes, pet accessories)
- Equip/unequip UI
- Cosmetics in reward shop
- Achievement popups / celebration animations
- Quest scroll visual effects
- Collection completion milestones

---

## Verification Plan

For each phase:

1. **Unit tests** — service-level tests for each new service (drop rolls, streak calculation, pet growth, quest progress)
2. **Integration tests** — signal → game loop → subsystem chain (e.g., clock-out triggers drop + quest progress + pet reaction)
3. **Seed data** — extend `seed_data` command with item catalog, pet species, sample quests
4. **Manual testing** — verify full flow via the frontend:
   - Clock in/out → check streak updates, drops appear, quest progresses
   - Complete chore → check drops, quest damage
   - Hatch a pet → feed → evolve to mount
   - Start quest → complete tasks → quest completes → rewards distributed
   - Check dashboard widgets render correctly
5. **Edge cases** — midnight rollover, streak reset on missed day, quest expiration, inventory overflow, double-tap prevention on habits
