// Reliquary Codex taxonomy — maps criterion_type (from apps/achievements/criteria.py)
// into seven manuscript chapters that mirror how the backend already groups
// badges by subsystem (time / projects / skills / economy / scholar / adventure /
// completionism + meta). Kept in a .js file so non-component exports don't trip
// react-refresh/only-export-components.

const RARITY_ORDER = { common: 0, uncommon: 1, rare: 2, epic: 3, legendary: 4 };

export const RARITY_KEYS = ['common', 'uncommon', 'rare', 'epic', 'legendary'];

export const COLLECTIONS = [
  {
    id: 'chronos',
    rubric: '§I',
    letter: 'C',
    name: 'Chronos',
    kicker: 'the cadence of hours',
    criteria: [
      'hours_worked',
      'hours_in_day',
      'days_worked',
      'first_clock_in',
      'early_bird',
      'late_night',
    ],
  },
  {
    id: 'ventures',
    rubric: '§II',
    letter: 'V',
    name: 'Ventures',
    kicker: 'the ledger of projects',
    criteria: [
      'projects_completed',
      'first_project',
      'category_projects',
      'materials_under_budget',
      'perfect_timecard',
      'photos_uploaded',
      'bounty_completed',
      'milestones_completed',
      'fast_project',
      'co_op_project_completed',
    ],
  },
  {
    id: 'mastery',
    rubric: '§III',
    letter: 'M',
    name: 'Mastery',
    kicker: 'the branches of skill',
    criteria: [
      'skill_level_reached',
      'skills_unlocked',
      'skill_categories_breadth',
      'subjects_completed',
      'cross_category_unlock',
      'category_mastery',
    ],
  },
  {
    id: 'coffers',
    rubric: '§IV',
    letter: 'G',
    name: 'Coffers',
    kicker: 'the weight of coin',
    criteria: [
      'total_earned',
      'total_coins_earned',
      'coins_spent_lifetime',
      'savings_goal_completed',
      'reward_redeemed',
    ],
  },
  {
    id: 'scholar',
    rubric: '§V',
    letter: 'Q',
    name: 'Scholar',
    kicker: 'the quill and the hour',
    criteria: [
      'homework_planned_ahead',
      'homework_on_time_count',
      'journal_entries_written',
      'journal_streak_days',
    ],
  },
  {
    id: 'adventure',
    rubric: '§VI',
    letter: 'A',
    name: 'Adventure',
    kicker: 'the wild and the wyrm',
    criteria: [
      'streak_days',
      'perfect_days_count',
      'streak_freeze_used',
      'habit_max_strength',
      'habit_count_at_strength',
      'habit_taps_lifetime',
      'chore_completions',
      'quest_completed',
      'boss_quests_completed',
      'collection_quests_completed',
      'pets_hatched',
      'pet_species_owned',
      'mounts_evolved',
    ],
  },
  {
    id: 'reliquary',
    rubric: '§VII',
    letter: 'R',
    name: 'Reliquary',
    kicker: 'the case of rarities',
    criteria: [
      'badges_earned_count',
      'cosmetic_set_owned',
      'cosmetic_full_set',
      'full_potion_shelf',
      'consumable_variety',
      'chronicle_milestones_logged',
      'grade_reached',
      'birthdays_logged',
    ],
  },
];

const CRITERION_TO_COLLECTION = Object.fromEntries(
  COLLECTIONS.flatMap((c) => c.criteria.map((k) => [k, c.id])),
);

export const COLLECTIONS_BY_ID = Object.fromEntries(COLLECTIONS.map((c) => [c.id, c]));

export function collectionForCriterion(criterionType) {
  return CRITERION_TO_COLLECTION[criterionType] ?? 'reliquary';
}

export function collectionForBadge(badge) {
  return COLLECTIONS_BY_ID[collectionForCriterion(badge?.criterion_type)] ?? COLLECTIONS_BY_ID.reliquary;
}

function blankRarityCounts() {
  return RARITY_KEYS.reduce((acc, k) => {
    acc[k] = { earned: 0, total: 0 };
    return acc;
  }, {});
}

export function rarityCounts(badges, earnedIds) {
  const counts = blankRarityCounts();
  const earnedSet = earnedIds instanceof Set ? earnedIds : new Set(earnedIds);
  for (const badge of badges ?? []) {
    const key = counts[badge?.rarity] ? badge.rarity : 'common';
    counts[key].total += 1;
    if (earnedSet.has(badge.id)) counts[key].earned += 1;
  }
  return counts;
}

function sortSigils(a, b) {
  if (a.earned && !b.earned) return -1;
  if (!a.earned && b.earned) return 1;
  if (a.earned && b.earned) {
    const at = a.earnedAt ? Date.parse(a.earnedAt) : 0;
    const bt = b.earnedAt ? Date.parse(b.earnedAt) : 0;
    return bt - at;
  }
  return (
    (RARITY_ORDER[a.badge.rarity] ?? 99) - (RARITY_ORDER[b.badge.rarity] ?? 99)
    || a.badge.name.localeCompare(b.badge.name)
  );
}

/**
 * Group badges into seven reliquary chapters. Returns an array in COLLECTIONS
 * order; every collection is always present (even when empty) so the codex
 * renders a consistent skeleton for fresh users.
 */
export function groupBadgesByCollection(allBadges, earnedBadges) {
  const earnedMap = new Map();
  for (const ub of earnedBadges ?? []) {
    if (ub?.badge?.id != null) earnedMap.set(ub.badge.id, ub.earned_at ?? null);
  }
  const buckets = new Map(COLLECTIONS.map((c) => [c.id, []]));
  for (const badge of allBadges ?? []) {
    if (!badge) continue;
    const id = collectionForCriterion(badge.criterion_type);
    const bucket = buckets.get(id) ?? buckets.get('reliquary');
    bucket.push({
      badge,
      earned: earnedMap.has(badge.id),
      earnedAt: earnedMap.get(badge.id) ?? null,
    });
  }
  return COLLECTIONS.map((collection) => {
    const badges = (buckets.get(collection.id) ?? []).sort(sortSigils);
    const earned = badges.filter((b) => b.earned).length;
    const earnedSet = new Set(badges.filter((b) => b.earned).map((b) => b.badge.id));
    return {
      collection,
      badges,
      earned,
      total: badges.length,
      rarityCounts: rarityCounts(badges.map((b) => b.badge), earnedSet),
    };
  });
}

/**
 * Natural-language unlock hint from a badge's criterion fields. Falls back to
 * badge.description when the criterion_type has no template — so new backend
 * criteria don't render as "undefined" in the sigil case.
 */
export function unlockHint(badge) {
  if (!badge) return '';
  const value = badge.criterion_value;
  const n = typeof value === 'number' ? value : Number(value);
  const hasN = Number.isFinite(n) && n > 0;
  const plural = hasN && n !== 1;

  switch (badge.criterion_type) {
    case 'hours_worked':
      return hasN ? `Log ${n} hour${plural ? 's' : ''} of tracked work` : 'Log tracked work';
    case 'hours_in_day':
      return hasN ? `Work ${n} hour${plural ? 's' : ''} in a single day` : 'Work a long day';
    case 'days_worked':
      return hasN ? `Clock in on ${n} different day${plural ? 's' : ''}` : 'Clock in across many days';
    case 'first_clock_in':
      return 'Clock in for the first time';
    case 'early_bird':
      return 'Clock in before 8 AM';
    case 'late_night':
      return 'Clock in after 9 PM';

    case 'projects_completed':
      return hasN ? `Complete ${n} project${plural ? 's' : ''}` : 'Complete projects';
    case 'first_project':
      return 'Complete your first project';
    case 'category_projects':
      return hasN ? `Complete ${n} project${plural ? 's' : ''} in one category` : 'Complete a category of projects';
    case 'materials_under_budget':
      return 'Finish a project under the materials budget';
    case 'perfect_timecard':
      return 'Ship a perfect weekly timecard';
    case 'photos_uploaded':
      return hasN ? `Upload ${n} project photo${plural ? 's' : ''}` : 'Upload project photos';
    case 'bounty_completed':
      return hasN ? `Claim ${n} bount${plural ? 'ies' : 'y'}` : 'Claim a bounty';
    case 'milestones_completed':
      return hasN ? `Complete ${n} milestone${plural ? 's' : ''}` : 'Complete milestones';
    case 'fast_project':
      return hasN ? `Finish a project in ${n} day${plural ? 's' : ''} or less` : 'Finish a project quickly';
    case 'co_op_project_completed':
      return 'Finish a co-op project with another maker';

    case 'skill_level_reached':
      return hasN ? `Reach level ${n} on any skill` : 'Reach a high skill level';
    case 'skills_unlocked':
      return hasN ? `Unlock ${n} skill${plural ? 's' : ''}` : 'Unlock skills';
    case 'skill_categories_breadth':
      return hasN ? `Earn XP in ${n} skill categor${plural ? 'ies' : 'y'}` : 'Spread XP across categories';
    case 'subjects_completed':
      return hasN ? `Complete ${n} subject${plural ? 's' : ''}` : 'Complete subjects';
    case 'cross_category_unlock':
      return 'Unlock a skill with a cross-category prerequisite';
    case 'category_mastery':
      return 'Master every skill in a category';

    case 'total_earned':
      return hasN ? `Earn $${n} lifetime` : 'Earn allowance';
    case 'total_coins_earned':
      return hasN ? `Earn ${n} coin${plural ? 's' : ''} lifetime` : 'Earn coins';
    case 'coins_spent_lifetime':
      return hasN ? `Spend ${n} coin${plural ? 's' : ''} lifetime` : 'Spend coins at the shop';
    case 'savings_goal_completed':
      return hasN ? `Fill ${n} savings goal${plural ? 's' : ''}` : 'Complete a savings goal';
    case 'reward_redeemed':
      return hasN ? `Redeem ${n} reward${plural ? 's' : ''}` : 'Redeem a reward';

    case 'homework_planned_ahead':
      return hasN ? `Plan ${n} assignment${plural ? 's' : ''} ahead of the due date` : 'Plan homework ahead';
    case 'homework_on_time_count':
      return hasN ? `Submit ${n} assignment${plural ? 's' : ''} on time` : 'Submit homework on time';
    case 'journal_entries_written':
      return hasN ? `Write ${n} journal entr${plural ? 'ies' : 'y'}` : 'Write journal entries';
    case 'journal_streak_days':
      return hasN ? `Journal ${n} day${plural ? 's' : ''} in a row` : 'Journal on a streak';

    case 'streak_days':
      return hasN ? `Reach a ${n}-day streak` : 'Hold a streak';
    case 'perfect_days_count':
      return hasN ? `Log ${n} perfect day${plural ? 's' : ''}` : 'Log a perfect day';
    case 'streak_freeze_used':
      return 'Use a streak freeze';
    case 'habit_max_strength':
      return 'Max out a habit\u2019s strength';
    case 'habit_count_at_strength':
      return hasN ? `Hold ${n} habits at full strength` : 'Stack strong habits';
    case 'habit_taps_lifetime':
      return hasN ? `Tap habits ${n} times lifetime` : 'Tap habits';
    case 'chore_completions':
      return hasN ? `Complete ${n} chore${plural ? 's' : ''}` : 'Complete chores';
    case 'quest_completed':
      return hasN ? `Finish ${n} quest${plural ? 's' : ''}` : 'Finish a quest';
    case 'boss_quests_completed':
      return hasN ? `Down ${n} boss quest${plural ? 's' : ''}` : 'Down a boss quest';
    case 'collection_quests_completed':
      return hasN ? `Complete ${n} collection quest${plural ? 's' : ''}` : 'Complete a collection quest';
    case 'pets_hatched':
      return hasN ? `Hatch ${n} pet${plural ? 's' : ''}` : 'Hatch a pet';
    case 'pet_species_owned':
      return hasN ? `Own ${n} pet species` : 'Raise varied pets';
    case 'mounts_evolved':
      return hasN ? `Evolve ${n} mount${plural ? 's' : ''}` : 'Evolve a mount';

    case 'badges_earned_count':
      return hasN ? `Earn ${n} badge${plural ? 's' : ''}` : 'Collect badges';
    case 'cosmetic_set_owned':
      return 'Own every cosmetic in a named set';
    case 'cosmetic_full_set':
      return 'Equip a cosmetic in all four slots';
    case 'full_potion_shelf':
      return 'Own every potion variant';
    case 'consumable_variety':
      return hasN ? `Own ${n} different consumables` : 'Stock varied consumables';
    case 'chronicle_milestones_logged':
      return hasN ? `Log ${n} chronicle milestone${plural ? 's' : ''}` : 'Log chronicle milestones';
    case 'grade_reached':
      return hasN ? `Reach grade ${n}` : 'Advance through grades';
    case 'birthdays_logged':
      return hasN ? `Celebrate ${n} birthday${plural ? 's' : ''}` : 'Celebrate a birthday';

    default:
      return badge.description || '';
  }
}

/**
 * Ladder siblings share a criterion_type and differ only by criterion_value —
 * a natural "Tier I → Tier II → …" progression. Returns the sorted series
 * including the supplied badge; callers can highlight the current entry by id.
 */
export function ladderSiblings(badge, allBadges) {
  if (!badge?.criterion_type) return [];
  const related = (allBadges ?? []).filter(
    (b) => b && b.criterion_type === badge.criterion_type && typeof b.criterion_value === 'number',
  );
  if (related.length < 2) return [];
  return related.slice().sort((a, b) => a.criterion_value - b.criterion_value);
}
