import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import ProgressionRewardBudgetControls from './ProgressionRewardBudgetControls';

const limits = { daily_coins: { min: 0, max: 100000, nullable: true } };
function Controls({ changed, error }) {
  const [budget, setBudget] = useState({ daily_coins: null });
  return <ProgressionRewardBudgetControls budget={budget} limits={limits} error={error} onChange={(value) => { setBudget(value); changed(value); }} />;
}

describe('Reward budget assumptions', () => {
  it('selects explicit per-child examples and accepts custom limits without confusing zero and uncapped', async () => {
    const changed = vi.fn();
    const { user } = renderWithProviders(<Controls changed={changed} />, { withAuth: false });
    expect(screen.getByRole('button', { name: 'Uncapped' })).toHaveAttribute('aria-pressed', 'true');
    for (const amount of [50, 100, 150]) {
      await user.click(screen.getByRole('button', { name: `${amount} Coins per child per day` }));
      expect(changed.mock.lastCall[0]).toEqual({ daily_coins: amount });
      expect(screen.getByRole('button', { name: `${amount} Coins per child per day` })).toHaveAttribute('aria-pressed', 'true');
    }
    const custom = screen.getByRole('spinbutton', { name: 'Daily reward budget per child (Coins)' });
    expect(custom).toHaveAttribute('min', '0');
    expect(custom).toHaveAttribute('max', '100000');
    expect(custom).toHaveAttribute('step', '1');
    await user.clear(custom);
    await user.type(custom, '0');
    expect(changed.mock.lastCall[0]).toEqual({ daily_coins: 0 });
    await user.clear(custom);
    expect(changed.mock.lastCall[0]).toEqual({ daily_coins: null });
    await user.type(custom, '75');
    expect(changed.mock.lastCall[0]).toEqual({ daily_coins: 75 });
    await user.click(screen.getByRole('button', { name: 'Uncapped' }));
    expect(changed.mock.lastCall[0]).toEqual({ daily_coins: null });
    expect(screen.getByText(/Excess Coins are omitted in the hypothetical journey, not deferred/)).toBeVisible();
    expect(screen.getByText(/expedition claims use it before pouch openings/)).toBeVisible();
  });

  it('links a server validation error to the retained custom value', () => {
    renderWithProviders(<Controls changed={() => {}} error="Choose a whole Coin budget." />, { withAuth: false });
    expect(screen.getByRole('spinbutton', { name: 'Daily reward budget per child (Coins)' })).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Choose a whole Coin budget.');
  });
});
