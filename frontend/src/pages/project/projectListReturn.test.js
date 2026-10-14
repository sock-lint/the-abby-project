import { describe, expect, it } from 'vitest';
import { captureProjectListReturn, projectListDestination } from './projectListReturn';

describe('Project return destination', () => {
  it('retains only supported list filters and never a supplied destination or credential', () => {
    const saved = captureProjectListReturn('?tab=other&status=in_review&type=bounty&child=3&q=wood&token=synthetic&returnTo=https://other.example/#private', 7, 480);
    expect(projectListDestination(saved, 7)).toEqual({
      to: '/quests?tab=ventures&status=in_review&type=bounty&child=3&q=wood',
      state: { projectListScroll: { userId: 7, top: 480 } },
    });
  });

  it('drops invalid filters, malformed position and a different account’s saved context', () => {
    const saved = captureProjectListReturn('?status=unknown&type=unknown&child=-1', 7, Infinity);
    expect(projectListDestination(saved, 7)).toEqual({ to: '/quests?tab=ventures', state: { projectListScroll: { userId: 7, top: 0 } } });
    expect(projectListDestination({ ...saved, search: '?q=previous-account' }, 8)).toEqual({ to: '/quests?tab=ventures', state: undefined });
    expect(projectListDestination({ userId: 8, search: { destination: 'https://other.example' }, scrollY: -500 }, 8).to).toBe('/quests?tab=ventures');
  });
});
