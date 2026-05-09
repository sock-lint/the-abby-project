import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../../test/render';
import DailyChallengeClaimModal from './DailyChallengeClaimModal';

const claim = { coins: 10, xp: 25, already_claimed: false };

describe('DailyChallengeClaimModal', () => {
  it('renders coin + xp totals and the challenge label', () => {
    renderWithProviders(
      <DailyChallengeClaimModal
        claim={claim}
        challengeLabel="Clock 1 hour"
        onDismiss={() => {}}
      />,
    );
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(screen.getByText(/clock 1 hour/i)).toBeInTheDocument();
    expect(screen.getByText(/\+10 coins · \+25 XP/)).toBeInTheDocument();
    expect(screen.getByText(/rite complete/i)).toBeInTheDocument();
  });

  it('calls onDismiss when Turn the page clicked', async () => {
    const onDismiss = vi.fn();
    const user = userEvent.setup();
    renderWithProviders(
      <DailyChallengeClaimModal claim={claim} onDismiss={onDismiss} />,
    );
    await user.click(screen.getByRole('button', { name: /turn the page/i }));
    expect(onDismiss).toHaveBeenCalled();
  });
});
