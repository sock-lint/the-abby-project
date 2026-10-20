import { describe, expect, it } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import LockedCatalogChallenges from './LockedCatalogChallenges';

describe('Pending catalog milestone previews', () => {
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
