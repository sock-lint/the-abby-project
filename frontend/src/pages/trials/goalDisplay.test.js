import { describe, expect, it } from 'vitest';
import { goalActionPath, goalDeadline, goalProgress, goalTargetSummary } from './goalDisplay';

describe('Measurable goal presentation', () => {
  it.each([
    { target: '1', progress: '0', expectedProgress: '0 / 1 active day', expectedTarget: '1 active day' },
    { target: '5', progress: '1', expectedProgress: '1 / 5 active days', expectedTarget: '5 active days' },
  ])('keeps the server day-based measure for a target of $target', ({ target, progress, expectedProgress, expectedTarget }) => {
    const goal = {
      metric: 'count', target, progress, unit: 'active days',
      what_counts: 'positive habit taps; counts once per active day in the saved household timezone',
    };
    expect(goalProgress(goal)).toBe(expectedProgress);
    expect(goalTargetSummary(goal)).toBe(`${expectedTarget} · ${goal.what_counts}`);
  });

  it('does not round an almost finished distance into apparent completion', () => {
    expect(goalProgress({ progress: '1.999', target: '2.000', unit: 'mi' })).toBe('1.999 / 2 miles');
  });
  it('shows the final included family day at an exclusive midnight deadline', () => {
    expect(goalDeadline('2026-10-19T07:00:00Z', 'America/Phoenix')).toBe('Oct 18');
  });
  it('does not expose nonapplication action URLs', () => {
    expect(goalActionPath({ path: '//foreign.example/collect' })).toBeNull();
    expect(goalActionPath({ path: 'https://foreign.example/collect' })).toBeNull();
  });
});
