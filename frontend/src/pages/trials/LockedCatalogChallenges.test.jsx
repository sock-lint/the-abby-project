import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import LockedCatalogChallenges from './LockedCatalogChallenges';
import discoveryLockedMilestone from '../../../../contracts/api/fixtures/challenge-discovery-locked-milestone.json';
import { spyHandler } from '../../test/spy';
import { server } from '../../test/server';

describe('Pending catalog milestone previews', () => {
  it('shows the actual alternative hatch requirement without starting, pinning or completing the future milestone', async () => {
    const write = spyHandler('post', /\/api\//, {});
    server.use(write.handler);
    const { user } = renderWithProviders(<LockedCatalogChallenges definitions={discoveryLockedMilestone.locked_catalog} />, { withAuth: false });
    const comingNext = within(screen.getByRole('region', { name: 'Coming next' }));
    expect(comingNext.getByText('Complete Reading Companion, or hatch Base Chick.')).toBeVisible();
    expect(comingNext.getByText('Not yet met')).toBeVisible();
    expect(comingNext.queryByRole('progressbar')).toBeNull();
    await user.click(comingNext.getByRole('button', { name: 'View requirements for Reading Voyager' }));
    const details = within(screen.getByRole('dialog', { name: 'Reading Voyager requirements' }));
    expect(details.getByText('Complete Reading Companion, or hatch Base Chick.')).toBeVisible();
    expect(details.getByText(/No deadline is running yet/)).toHaveTextContent('84 days after it starts.');
    expect(details.queryByRole('button', { name: /start|pin|begin/i })).toBeNull();
    expect(write.calls).toHaveLength(0);
  });

  it('uses confirmed requirement flags rather than inferring an unlock from skill numbers', async () => {
    const definition = { id: 77, name: 'Reading Voyager', duration_days: 56,
      required_skill: 4, required_skill_level: 1,
      milestone_eligibility: { unlocked: false, locked_reasons: ['Complete Reading Companion'], requirements: [
        { kind: 'skill', met: false, current_level: 6, required_level: 1, description: 'Reach Reading Comprehension level 1' },
      ] } };
    const { user } = renderWithProviders(<LockedCatalogChallenges definitions={[definition]} />, { withAuth: false });
    expect(screen.getByText('Locked challenge')).toBeVisible();
    expect(screen.getByText('Not yet met')).toBeVisible();
    expect(screen.queryByText('Requirements met')).toBeNull();
    await user.click(screen.getByRole('button', { name: 'View requirements for Reading Voyager' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText(/No deadline is running yet/)).toBeVisible();
    expect(dialog.queryByRole('button', { name: /start|pin|begin/i })).toBeNull();
  });

  it('keeps missing eligibility unknown and never fabricates progress or a deadline', () => {
    renderWithProviders(<LockedCatalogChallenges definitions={[{ id: 77, name: 'Reading Voyager' }]} />, { withAuth: false });
    expect(screen.getByText('Availability unavailable')).toBeVisible();
    expect(screen.getByText(/Requirement details are unavailable/)).toBeVisible();
    expect(screen.queryByText('Requirements met')).toBeNull();
    expect(screen.queryByRole('progressbar')).toBeNull();
    expect(screen.queryByRole('time')).toBeNull();
  });

  it('omits the pending section for older responses or an empty list', () => {
    renderWithProviders(<LockedCatalogChallenges />, { withAuth: false });
    expect(screen.queryByRole('region', { name: 'Coming next' })).toBeNull();
  });
});
