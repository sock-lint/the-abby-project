import { describe, expect, it } from 'vitest';
import { goalActionPath, goalDeadline, goalProgress } from './goalDisplay';

describe('Measurable goal presentation', () => {
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
