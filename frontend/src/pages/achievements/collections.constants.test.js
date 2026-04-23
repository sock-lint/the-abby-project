import { describe, it, expect } from 'vitest';
import {
  COLLECTIONS,
  COLLECTIONS_BY_ID,
  collectionForBadge,
  collectionForCriterion,
  groupBadgesByCollection,
  ladderSiblings,
  rarityCounts,
  unlockHint,
} from './collections.constants';

describe('collections.constants', () => {
  describe('COLLECTIONS taxonomy', () => {
    it('ships seven chapters in rubric order', () => {
      expect(COLLECTIONS).toHaveLength(7);
      expect(COLLECTIONS.map((c) => c.rubric)).toEqual([
        '§I', '§II', '§III', '§IV', '§V', '§VI', '§VII',
      ]);
    });

    it('keeps every collection id unique and letter a single character', () => {
      const ids = new Set(COLLECTIONS.map((c) => c.id));
      expect(ids.size).toBe(COLLECTIONS.length);
      for (const c of COLLECTIONS) {
        expect(c.letter).toHaveLength(1);
      }
    });

    it('exports an id→collection lookup', () => {
      expect(COLLECTIONS_BY_ID.chronos.name).toBe('Chronos');
      expect(COLLECTIONS_BY_ID.reliquary.rubric).toBe('§VII');
    });
  });

  describe('collectionForCriterion', () => {
    it.each([
      ['hours_worked', 'chronos'],
      ['first_clock_in', 'chronos'],
      ['projects_completed', 'ventures'],
      ['milestones_completed', 'ventures'],
      ['skill_level_reached', 'mastery'],
      ['category_mastery', 'mastery'],
      ['total_earned', 'coffers'],
      ['savings_goal_completed', 'coffers'],
      ['homework_on_time_count', 'scholar'],
      ['journal_entries_written', 'scholar'],
      ['journal_streak_days', 'scholar'],
      ['streak_days', 'adventure'],
      ['pets_hatched', 'adventure'],
      ['mounts_evolved', 'adventure'],
      ['badges_earned_count', 'reliquary'],
      ['birthdays_logged', 'reliquary'],
    ])('%s → %s', (criterion, collectionId) => {
      expect(collectionForCriterion(criterion)).toBe(collectionId);
    });

    it('falls back to reliquary for unknown criterion_types', () => {
      expect(collectionForCriterion('brand_new_future_criterion')).toBe('reliquary');
      expect(collectionForCriterion(undefined)).toBe('reliquary');
    });
  });

  describe('collectionForBadge', () => {
    it('returns the full collection object', () => {
      const c = collectionForBadge({ criterion_type: 'quest_completed' });
      expect(c.id).toBe('adventure');
      expect(c.name).toBe('Adventure');
    });
  });

  describe('groupBadgesByCollection', () => {
    const badges = [
      { id: 1, name: 'Apprentice', rarity: 'common', criterion_type: 'projects_completed', criterion_value: 1 },
      { id: 2, name: 'Journeyman', rarity: 'uncommon', criterion_type: 'projects_completed', criterion_value: 5 },
      { id: 3, name: 'Night Owl', rarity: 'rare', criterion_type: 'late_night', criterion_value: 1 },
      { id: 4, name: 'Mystery', rarity: 'epic', criterion_type: 'some_future_thing' },
    ];

    it('returns all seven chapters in COLLECTIONS order', () => {
      const grouped = groupBadgesByCollection(badges, []);
      expect(grouped.map((g) => g.collection.id)).toEqual(
        COLLECTIONS.map((c) => c.id),
      );
    });

    it('buckets each badge into its chapter', () => {
      const grouped = groupBadgesByCollection(badges, []);
      const byId = Object.fromEntries(grouped.map((g) => [g.collection.id, g]));
      expect(byId.ventures.total).toBe(2);
      expect(byId.chronos.total).toBe(1);
      expect(byId.reliquary.total).toBe(1);
    });

    it('sorts earned badges first by earned_at desc within a chapter', () => {
      const earned = [
        { badge: { id: 2 }, earned_at: '2026-04-20' },
        { badge: { id: 1 }, earned_at: '2026-04-01' },
      ];
      const grouped = groupBadgesByCollection(badges, earned);
      const ventures = grouped.find((g) => g.collection.id === 'ventures');
      expect(ventures.badges.map((b) => b.badge.id)).toEqual([2, 1]);
      expect(ventures.earned).toBe(2);
    });

    it('sorts unearned by rarity then name', () => {
      const local = [
        { id: 10, name: 'Zeta', rarity: 'common', criterion_type: 'projects_completed' },
        { id: 11, name: 'Alpha', rarity: 'rare', criterion_type: 'projects_completed' },
        { id: 12, name: 'Mid', rarity: 'common', criterion_type: 'projects_completed' },
      ];
      const grouped = groupBadgesByCollection(local, []);
      const ventures = grouped.find((g) => g.collection.id === 'ventures');
      expect(ventures.badges.map((b) => b.badge.id)).toEqual([12, 10, 11]);
    });
  });

  describe('rarityCounts', () => {
    it('sums earned + total per rarity', () => {
      const badges = [
        { id: 1, rarity: 'common' },
        { id: 2, rarity: 'common' },
        { id: 3, rarity: 'legendary' },
      ];
      const counts = rarityCounts(badges, new Set([1, 3]));
      expect(counts.common).toEqual({ earned: 1, total: 2 });
      expect(counts.legendary).toEqual({ earned: 1, total: 1 });
      expect(counts.rare).toEqual({ earned: 0, total: 0 });
    });

    it('accepts an array of ids as the earned argument', () => {
      const counts = rarityCounts([{ id: 7, rarity: 'epic' }], [7]);
      expect(counts.epic).toEqual({ earned: 1, total: 1 });
    });
  });

  describe('unlockHint', () => {
    // Covers every criterion_type in apps/achievements/criteria.py so the
    // switch can never regress into an "undefined" rendering. Singular vs
    // plural paths are exercised together where applicable.
    it.each([
      // Chronos
      [{ criterion_type: 'hours_worked', criterion_value: 10 }, 'Log 10 hours of tracked work'],
      [{ criterion_type: 'hours_worked', criterion_value: 1 }, 'Log 1 hour of tracked work'],
      [{ criterion_type: 'hours_worked' }, 'Log tracked work'],
      [{ criterion_type: 'hours_in_day', criterion_value: 5 }, 'Work 5 hours in a single day'],
      [{ criterion_type: 'hours_in_day' }, 'Work a long day'],
      [{ criterion_type: 'days_worked', criterion_value: 5 }, 'Clock in on 5 different days'],
      [{ criterion_type: 'days_worked', criterion_value: 1 }, 'Clock in on 1 different day'],
      [{ criterion_type: 'days_worked' }, 'Clock in across many days'],
      [{ criterion_type: 'first_clock_in' }, 'Clock in for the first time'],
      [{ criterion_type: 'early_bird' }, 'Clock in before 8 AM'],
      [{ criterion_type: 'late_night' }, 'Clock in after 9 PM'],
      // Ventures
      [{ criterion_type: 'projects_completed', criterion_value: 10 }, 'Complete 10 projects'],
      [{ criterion_type: 'projects_completed', criterion_value: 1 }, 'Complete 1 project'],
      [{ criterion_type: 'projects_completed' }, 'Complete projects'],
      [{ criterion_type: 'first_project' }, 'Complete your first project'],
      [{ criterion_type: 'category_projects', criterion_value: 5 }, 'Complete 5 projects in one category'],
      [{ criterion_type: 'category_projects' }, 'Complete a category of projects'],
      [{ criterion_type: 'materials_under_budget' }, 'Finish a project under the materials budget'],
      [{ criterion_type: 'perfect_timecard' }, 'Ship a perfect weekly timecard'],
      [{ criterion_type: 'photos_uploaded', criterion_value: 10 }, 'Upload 10 project photos'],
      [{ criterion_type: 'photos_uploaded' }, 'Upload project photos'],
      [{ criterion_type: 'bounty_completed', criterion_value: 3 }, 'Claim 3 bounties'],
      [{ criterion_type: 'bounty_completed', criterion_value: 1 }, 'Claim 1 bounty'],
      [{ criterion_type: 'bounty_completed' }, 'Claim a bounty'],
      [{ criterion_type: 'milestones_completed', criterion_value: 10 }, 'Complete 10 milestones'],
      [{ criterion_type: 'milestones_completed' }, 'Complete milestones'],
      [{ criterion_type: 'fast_project', criterion_value: 3 }, 'Finish a project in 3 days or less'],
      [{ criterion_type: 'fast_project' }, 'Finish a project quickly'],
      [{ criterion_type: 'co_op_project_completed' }, 'Finish a co-op project with another maker'],
      // Mastery
      [{ criterion_type: 'skill_level_reached', criterion_value: 5 }, 'Reach level 5 on any skill'],
      [{ criterion_type: 'skill_level_reached' }, 'Reach a high skill level'],
      [{ criterion_type: 'skills_unlocked', criterion_value: 10 }, 'Unlock 10 skills'],
      [{ criterion_type: 'skills_unlocked' }, 'Unlock skills'],
      [{ criterion_type: 'skill_categories_breadth', criterion_value: 5 }, 'Earn XP in 5 skill categories'],
      [{ criterion_type: 'skill_categories_breadth', criterion_value: 1 }, 'Earn XP in 1 skill category'],
      [{ criterion_type: 'skill_categories_breadth' }, 'Spread XP across categories'],
      [{ criterion_type: 'subjects_completed', criterion_value: 5 }, 'Complete 5 subjects'],
      [{ criterion_type: 'subjects_completed' }, 'Complete subjects'],
      [{ criterion_type: 'cross_category_unlock' }, 'Unlock a skill with a cross-category prerequisite'],
      [{ criterion_type: 'category_mastery' }, 'Master every skill in a category'],
      // Coffers
      [{ criterion_type: 'total_earned', criterion_value: 100 }, 'Earn $100 lifetime'],
      [{ criterion_type: 'total_earned' }, 'Earn allowance'],
      [{ criterion_type: 'total_coins_earned', criterion_value: 500 }, 'Earn 500 coins lifetime'],
      [{ criterion_type: 'total_coins_earned' }, 'Earn coins'],
      [{ criterion_type: 'coins_spent_lifetime', criterion_value: 100 }, 'Spend 100 coins lifetime'],
      [{ criterion_type: 'coins_spent_lifetime' }, 'Spend coins at the shop'],
      [{ criterion_type: 'savings_goal_completed', criterion_value: 3 }, 'Fill 3 savings goals'],
      [{ criterion_type: 'savings_goal_completed' }, 'Complete a savings goal'],
      [{ criterion_type: 'reward_redeemed', criterion_value: 5 }, 'Redeem 5 rewards'],
      [{ criterion_type: 'reward_redeemed' }, 'Redeem a reward'],
      // Scholar
      [{ criterion_type: 'homework_planned_ahead', criterion_value: 5 }, 'Plan 5 assignments ahead of the due date'],
      [{ criterion_type: 'homework_planned_ahead' }, 'Plan homework ahead'],
      [{ criterion_type: 'homework_on_time_count', criterion_value: 10 }, 'Submit 10 assignments on time'],
      [{ criterion_type: 'homework_on_time_count' }, 'Submit homework on time'],
      [{ criterion_type: 'journal_entries_written', criterion_value: 10 }, 'Write 10 journal entries'],
      [{ criterion_type: 'journal_entries_written' }, 'Write journal entries'],
      [{ criterion_type: 'journal_streak_days', criterion_value: 7 }, 'Journal 7 days in a row'],
      [{ criterion_type: 'journal_streak_days' }, 'Journal on a streak'],
      // Adventure
      [{ criterion_type: 'streak_days', criterion_value: 7 }, 'Reach a 7-day streak'],
      [{ criterion_type: 'streak_days' }, 'Hold a streak'],
      [{ criterion_type: 'perfect_days_count', criterion_value: 10 }, 'Log 10 perfect days'],
      [{ criterion_type: 'perfect_days_count' }, 'Log a perfect day'],
      [{ criterion_type: 'streak_freeze_used' }, 'Use a streak freeze'],
      [{ criterion_type: 'habit_max_strength' }, 'Max out a habit\u2019s strength'],
      [{ criterion_type: 'habit_count_at_strength', criterion_value: 5 }, 'Hold 5 habits at full strength'],
      [{ criterion_type: 'habit_count_at_strength' }, 'Stack strong habits'],
      [{ criterion_type: 'habit_taps_lifetime', criterion_value: 500 }, 'Tap habits 500 times lifetime'],
      [{ criterion_type: 'habit_taps_lifetime' }, 'Tap habits'],
      [{ criterion_type: 'chore_completions', criterion_value: 25 }, 'Complete 25 chores'],
      [{ criterion_type: 'chore_completions' }, 'Complete chores'],
      [{ criterion_type: 'quest_completed', criterion_value: 5 }, 'Finish 5 quests'],
      [{ criterion_type: 'quest_completed' }, 'Finish a quest'],
      [{ criterion_type: 'boss_quests_completed', criterion_value: 3 }, 'Down 3 boss quests'],
      [{ criterion_type: 'boss_quests_completed' }, 'Down a boss quest'],
      [{ criterion_type: 'collection_quests_completed', criterion_value: 3 }, 'Complete 3 collection quests'],
      [{ criterion_type: 'collection_quests_completed' }, 'Complete a collection quest'],
      [{ criterion_type: 'pets_hatched', criterion_value: 3 }, 'Hatch 3 pets'],
      [{ criterion_type: 'pets_hatched' }, 'Hatch a pet'],
      [{ criterion_type: 'pet_species_owned', criterion_value: 5 }, 'Own 5 pet species'],
      [{ criterion_type: 'pet_species_owned' }, 'Raise varied pets'],
      [{ criterion_type: 'mounts_evolved', criterion_value: 3 }, 'Evolve 3 mounts'],
      [{ criterion_type: 'mounts_evolved' }, 'Evolve a mount'],
      // Reliquary
      [{ criterion_type: 'badges_earned_count', criterion_value: 25 }, 'Earn 25 badges'],
      [{ criterion_type: 'badges_earned_count' }, 'Collect badges'],
      [{ criterion_type: 'cosmetic_set_owned' }, 'Own every cosmetic in a named set'],
      [{ criterion_type: 'cosmetic_full_set' }, 'Equip a cosmetic in all four slots'],
      [{ criterion_type: 'full_potion_shelf' }, 'Own every potion variant'],
      [{ criterion_type: 'consumable_variety', criterion_value: 10 }, 'Own 10 different consumables'],
      [{ criterion_type: 'consumable_variety' }, 'Stock varied consumables'],
      [{ criterion_type: 'chronicle_milestones_logged', criterion_value: 5 }, 'Log 5 chronicle milestones'],
      [{ criterion_type: 'chronicle_milestones_logged' }, 'Log chronicle milestones'],
      [{ criterion_type: 'grade_reached', criterion_value: 9 }, 'Reach grade 9'],
      [{ criterion_type: 'grade_reached' }, 'Advance through grades'],
      [{ criterion_type: 'birthdays_logged', criterion_value: 3 }, 'Celebrate 3 birthdays'],
      [{ criterion_type: 'birthdays_logged' }, 'Celebrate a birthday'],
    ])('maps %o → %s', (badge, expected) => {
      expect(unlockHint(badge)).toBe(expected);
    });

    it('falls back to description for unknown criterion_types', () => {
      expect(unlockHint({ criterion_type: 'future_thing', description: 'Do a thing' }))
        .toBe('Do a thing');
    });

    it('returns empty string when no badge is supplied', () => {
      expect(unlockHint(null)).toBe('');
    });

    it('returns empty string for unknown criterion with no description', () => {
      expect(unlockHint({ criterion_type: 'future_thing' })).toBe('');
    });

    it('treats criterion_value as non-positive when it is a string', () => {
      // Number('abc') is NaN — the hasN guard rejects and we drop to the
      // "no value" branch of the template.
      expect(unlockHint({ criterion_type: 'projects_completed', criterion_value: 'abc' }))
        .toBe('Complete projects');
    });
  });

  describe('ladderSiblings', () => {
    it('returns the sorted series when two+ badges share a criterion_type', () => {
      const badges = [
        { id: 1, criterion_type: 'projects_completed', criterion_value: 1 },
        { id: 2, criterion_type: 'projects_completed', criterion_value: 10 },
        { id: 3, criterion_type: 'projects_completed', criterion_value: 50 },
        { id: 4, criterion_type: 'streak_days', criterion_value: 7 },
      ];
      const siblings = ladderSiblings({ id: 2, criterion_type: 'projects_completed', criterion_value: 10 }, badges);
      expect(siblings.map((b) => b.id)).toEqual([1, 2, 3]);
    });

    it('returns empty when fewer than two siblings exist', () => {
      const badges = [
        { id: 1, criterion_type: 'projects_completed', criterion_value: 10 },
      ];
      expect(ladderSiblings(badges[0], badges)).toEqual([]);
    });

    it('returns empty when criterion_type is missing', () => {
      expect(ladderSiblings({ id: 1 }, [])).toEqual([]);
    });
  });
});
