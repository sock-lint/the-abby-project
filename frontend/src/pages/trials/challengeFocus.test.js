import { describe, expect, it } from 'vitest';
import { buildChallengeGoal } from '../../test/challenges';
import { challengeFocus } from './challengeFocus';

describe('challenge focus presentation', () => {
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
