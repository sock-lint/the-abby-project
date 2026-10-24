import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { screen, within } from '@testing-library/react';
import { renderWithProviders } from '../../test/render';
import { selectDropdown } from '../../test/selectDropdown';
import ProgressionEconomyControls from './ProgressionEconomyControls';
import { economyDefaults, economyMetadata, offerDefaults } from './progressionEconomyTestData';

function Controls({ initial = economyDefaults, changed, example = () => {} }) {
  const [economy, setEconomy] = useState(initial);
  return <ProgressionEconomyControls economy={economy} metadata={economyMetadata} onChange={(value) => { setEconomy(value); changed?.(value); }} onExample={example} />;
}

describe('Purchasing assumptions', () => {
  it('starts new offers at the small-reward guide and changes an existing price only after applying a suggestion', async () => {
    const changed = vi.fn();
    const { user } = renderWithProviders(<Controls initial={{ ...economyDefaults, enabled: true, offers: [{ ...offerDefaults, key: 'existing', coin_price: 713 }] }} changed={changed} />, { withAuth: false });
    const existing = within(screen.getByRole('group', { name: 'Reward 1' }));
    expect(existing.getByRole('spinbutton', { name: 'Price (Coins)' })).toHaveValue(713);
    const daily = existing.getByLabelText('Estimated Coins per active day');
    await user.clear(daily);
    await user.type(daily, '40');
    expect(changed).not.toHaveBeenCalled();
    expect(existing.getByRole('spinbutton', { name: 'Price (Coins)' })).toHaveValue(713);
    await user.click(existing.getByRole('button', { name: 'Medium · 10 active days · 400 Coins' }));
    expect(changed.mock.lastCall[0].offers[0].coin_price).toBe(400);
    await user.click(screen.getByRole('button', { name: 'Add reward offer' }));
    expect(changed.mock.lastCall[0].offers.map((offer) => offer.coin_price)).toEqual([400, 150]);
  });

  it('starts off and accepts dollar costs as integer cents without confusing blank limits with zero', async () => {
    const changed = vi.fn();
    const { user } = renderWithProviders(<Controls changed={changed} />, { withAuth: false });
    expect(screen.getByRole('checkbox', { name: 'Model purchases and family costs' })).not.toBeChecked();
    await user.click(screen.getByRole('checkbox', { name: 'Model purchases and family costs' }));
    await user.click(screen.getByRole('button', { name: 'Add reward offer' }));
    const reward = within(screen.getByRole('group', { name: 'Reward 1' }));
    await user.clear(reward.getByRole('spinbutton', { name: 'Family cost per purchase ($)' }));
    await user.type(reward.getByRole('spinbutton', { name: 'Family cost per purchase ($)' }), '2.75');
    expect(changed.mock.lastCall[0].offers[0].family_cost_cents).toBe(275);
    const budget = screen.getByRole('spinbutton', { name: 'Monthly family cost budget per child ($)' });
    await user.type(budget, '0');
    expect(changed.mock.lastCall[0].monthly_family_budget_cents).toBe(0);
    await user.clear(budget);
    expect(changed.mock.lastCall[0].monthly_family_budget_cents).toBeNull();
    await user.type(reward.getByRole('spinbutton', { name: 'Stock per child (blank = unlimited)' }), '0');
    expect(changed.mock.lastCall[0].offers[0].stock).toBe(0);
  });

  it('keeps list order as priority, preserves repeat and stock choices, and removes only the selected offer', async () => {
    const changed = vi.fn();
    const initial = { ...economyDefaults, enabled: true, offers: [{ ...offerDefaults, key: 'first', label: 'First', repeat_every_days: 7, stock: 2 }, { ...offerDefaults, key: 'second', label: 'Second' }] };
    const { user } = renderWithProviders(<Controls initial={initial} changed={changed} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Move reward 2 earlier' }));
    expect(changed.mock.lastCall[0].offers.map((offer) => offer.key)).toEqual(['second', 'first']);
    expect(changed.mock.lastCall[0].offers[1]).toMatchObject({ repeat_every_days: 7, stock: 2 });
    await user.click(screen.getByRole('button', { name: 'Remove reward 1' }));
    expect(changed.mock.lastCall[0].offers.map((offer) => offer.key)).toEqual(['first']);
  });

  it('quotes print minutes using the explicit rate and treats an unset rate as free', async () => {
    const changed = vi.fn();
    const { user } = renderWithProviders(<Controls initial={{ ...economyDefaults, enabled: true }} changed={changed} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Add print offer' }));
    expect(screen.getByText(/No print rate is set: this print costs 0 Coins/)).toBeVisible();
    await user.click(screen.getByText('Printing quote and monthly limits'));
    await user.type(screen.getByRole('spinbutton', { name: 'Print minutes per Coin (blank = free)' }), '10');
    expect(screen.getByText(/Scenario print quote: 5 Coins for 45 minutes/)).toBeVisible();
    expect(changed.mock.lastCall[0].offers[0].coin_price).toBe(5);
    const reward = within(screen.getByRole('group', { name: 'Reward 1' }));
    expect(reward.getByRole('spinbutton', { name: 'Print minutes' })).toHaveAttribute('min', '1');
    await selectDropdown(user, reward.getByRole('combobox', { name: 'Reward type' }), 'real_world');
    expect(changed.mock.lastCall[0].offers[0]).toMatchObject({ kind: 'real_world', print_minutes: 0, print_grams: 0 });
  });

  it('keeps earned money and top-ups explicit, and calls the named example action', async () => {
    const changed = vi.fn();
    const example = vi.fn();
    const { user } = renderWithProviders(<Controls changed={changed} example={example} />, { withAuth: false });
    await user.click(screen.getByRole('button', { name: 'Load purchasing example (90 days, 10 children)' }));
    expect(example).toHaveBeenCalledOnce();
    await user.click(screen.getByRole('checkbox', { name: 'Model purchases and family costs' }));
    await user.click(screen.getByText('Earned money and optional Coin top-ups'));
    await user.clear(screen.getByRole('spinbutton', { name: 'Money earned per approved chore ($)' }));
    await user.type(screen.getByRole('spinbutton', { name: 'Money earned per approved chore ($)' }), '1.01');
    expect(changed.mock.lastCall[0].chore_money_cents).toBe(101);
    await user.click(screen.getByRole('checkbox', { name: 'Top up purchase shortfalls using earned money' }));
    await user.type(screen.getByRole('spinbutton', { name: 'Monthly money-to-Coins exchange limit ($)' }), '3.25');
    expect(changed.mock.lastCall[0]).toMatchObject({ exchange_shortfalls: true, monthly_exchange_limit_cents: 325 });
  });
});
