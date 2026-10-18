import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import report from '../../../../contracts/api/fixtures/progression-lab-commitment-report.json';
import ProgressionCommitmentReport from './ProgressionCommitmentReport';

describe('Commitment forecast evidence', () => {
  it('shows actual server commitments, payments, outstanding promises and unavailable paths separately', async () => {
    const { user } = renderWithProviders(<ProgressionCommitmentReport commitment={report.reward_commitment} />);
    expect(screen.getByRole('region', { name: 'Reward commitment forecast' })).toBeVisible();
    expect(screen.getByText('Potential duplicate salvage reserved')).toBeVisible();
    expect(screen.getByText('All pouch Coins paid')).toBeVisible();
    expect(screen.getByText('Pouch value awaiting claim or opening')).toBeVisible();
    expect(screen.getByText(/Removing access is not additional content runway/)).toBeVisible();
    await user.click(screen.getByText('Pouch promises by source'));
    expect(screen.getByRole('table', { name: 'Mean pouch Coins per child' })).toBeVisible();
    await user.click(screen.getByText('Commitment model assumptions'));
    expect(screen.getByText(/Late claims or pouch opening can pay more than 100 Coins/)).toBeVisible();
  });
  it('does not attribute commitment results to installed or legacy envelope reports', () => {
    renderWithProviders(<ProgressionCommitmentReport commitment={{ enabled: false }} />);
    expect(screen.queryByRole('region', { name: 'Reward commitment forecast' })).toBeNull();
  });
});
