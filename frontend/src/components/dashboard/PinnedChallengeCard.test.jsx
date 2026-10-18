import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useLocation } from 'react-router-dom';
import { renderWithProviders, screen } from '../../test/render';
import { buildChallengeGoal } from '../../test/challenges';
import PinnedChallengeCard from './PinnedChallengeCard';
import { resolvePedestalImage } from '../../pedestal/pedestalRelease';

vi.mock('../../pedestal/pedestalRelease', () => ({ resolvePedestalImage: vi.fn() }));
beforeEach(() => resolvePedestalImage.mockReturnValue(null));

function LocationProbe() {
  const location = useLocation();
  return <span data-testid="pin-location">{location.pathname}{location.search}</span>;
}

describe('Pinned challenge on Today', () => {
  it('keeps the saved goal and fractional progress inside the tall kit canvas', () => {
    const { container } = renderWithProviders(<PinnedChallengeCard goal={buildChallengeGoal()} />, { withAuth: false });
    expect(container.querySelector('[data-achievement-card="tall"]')).toBeInTheDocument();
    expect(container.querySelector('[data-pedestal-image="card-front-light"]')).toBeNull();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Run 2 miles this week' })).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0.75');
    expect(screen.getByRole('button', { name: 'Log a run' })).toBeEnabled();
  });

  it('provides a choice when no goal is pinned without pretending progress has stopped', async () => {
    const { user } = renderWithProviders(<><PinnedChallengeCard /><LocationProbe /></>, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Choose a challenge to pin' }));
    expect(screen.getByTestId('pin-location')).toHaveTextContent('/quests?tab=trials');
  });

  it('shows fractional server progress and opens the exact eligible work', async () => {
    const { user } = renderWithProviders(<><PinnedChallengeCard goal={buildChallengeGoal()} /><LocationProbe /></>, { withAuth: false });
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0.75');
    expect(screen.getByText('0.75 / 2 miles')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Log a run' }));
    expect(screen.getByTestId('pin-location')).toHaveTextContent('/quests?tab=movement&log=1&movement_type=3');
  });

  it('opens the pinned occurrence detail rather than another goal', async () => {
    const { user } = renderWithProviders(<><PinnedChallengeCard goal={buildChallengeGoal()} /><LocationProbe /></>, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'View challenge' }));
    expect(screen.getByTestId('pin-location')).toHaveTextContent('/quests?tab=trials&goal=goal%3A11');
  });
});
