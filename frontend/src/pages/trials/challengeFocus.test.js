import { describe, expect, it } from 'vitest';
import { buildChallengeGoal } from '../../test/challenges';
import { challengeFocus } from './challengeFocus';

describe('challenge focus presentation', () => {
  it('surfaces at most three unopened one-time catalog goals without duplicating pins or other previews', () => {
    const goals = Array.from({ length: 5 }, (_, i) => buildChallengeGoal({
      id: `goal:new-${i}`, name: `Scene ${i}`, origin: 'catalog', progress: '0',
      catalog_repeatable: false, first_details_opened_at: null,
      starts_at: `2026-10-${12 + i}T07:00:00Z`,
    }));
    const excluded = [
      buildChallengeGoal({ id: 'goal:repeat', origin: 'catalog', catalog_repeatable: true }),
      buildChallengeGoal({ id: 'goal:opened', origin: 'catalog', catalog_repeatable: false, first_details_opened_at: '2026-10-18T19:00:00Z' }),
      buildChallengeGoal({ id: 'goal:future', origin: 'catalog', catalog_repeatable: false, status: 'upcoming' }),
      buildChallengeGoal({ id: 'goal:parent', origin: 'parent', catalog_repeatable: false }),
      buildChallengeGoal({ id: 'legacy:1', origin: 'legacy', catalog_repeatable: false }),
    ];
    const focus = challengeFocus([...goals, ...excluded], goals[4]);
    expect(focus.explore.map((goal) => goal.id)).toEqual(['goal:new-3', 'goal:new-2', 'goal:new-1']);
    const previewIds = [...focus.explore, ...focus.bonusPreview, ...focus.otherBonuses, focus.pinned].map((goal) => goal.id);
    expect(new Set(previewIds).size).toBe(previewIds.length);
    expect(focus.otherBonuses).toContain(goals[0]);
    expect(excluded[1].first_details_opened_at).toBe('2026-10-18T19:00:00Z');
  });

  it('retains every bonus outside the preview, including saved legacy goals, without modifying server data', () => {
    const goals = Array.from({ length: 43 }, (_, i) => buildChallengeGoal({ id: `goal:${i}`, name: `Bonus ${i}`, origin: i === 0 ? 'legacy' : 'catalog', progress: String(i) }));
    const before = JSON.stringify(goals);
    const focus = challengeFocus(goals, null);
    expect(focus.bonusPreview).toHaveLength(3);
    expect(focus.otherBonuses).toHaveLength(40);
    expect(new Set([...focus.bonusPreview, ...focus.otherBonuses].map((goal) => goal.id)).size).toBe(43);
    expect(focus.otherBonuses.find((goal) => goal.id === 'goal:0')?.origin).toBe('legacy');
    expect(JSON.stringify(goals)).toBe(before);
  });

  it('keeps upcoming parent goals and completed history without treating a completed pin as active', () => {
    const upcoming = buildChallengeGoal({ id: 'goal:future', status: 'upcoming' });
    const completed = buildChallengeGoal({ id: 'goal:done', status: 'completed' });
    const focus = challengeFocus([upcoming, completed], completed);
    expect(focus.pinned).toBeNull();
    expect(focus.upcoming).toEqual([upcoming]);
    expect(focus.history).toEqual([completed]);
    expect(focus.parentCount).toBe(1);
  });
});
