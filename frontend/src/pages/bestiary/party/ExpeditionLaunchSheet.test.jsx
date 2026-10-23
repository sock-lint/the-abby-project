import { describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExpeditionLaunchSheet from './ExpeditionLaunchSheet';
import { startExpedition } from '../../../api';

vi.mock('../../../api', () => ({ startExpedition: vi.fn() }));

const mount = { id: 51, species: { name: 'Chick', slug: 'chick' }, potion: { slug: 'base' } };

describe('Expedition payout choices', () => {
  it('shows the reduced payout before starting each new trip', () => {
    render(<ExpeditionLaunchSheet mount={mount} onDismiss={vi.fn()} />);
    for (const [label, coins, items] of [
      ['Short expedition', 3, '1 item'],
      ['Standard expedition', 7, '2 items'],
      ['Long expedition', 15, '3 items'],
    ]) {
      const choice = screen.getByRole('button', { name: new RegExp(label) });
      expect(within(choice).getByText(`~${coins} coins`)).toBeVisible();
      expect(within(choice).getByText(items)).toBeVisible();
    }
    expect(startExpedition).not.toHaveBeenCalled();
  });

  it('submits only the chosen tier and displays no locally awarded balance', async () => {
    const launched = vi.fn();
    const dismiss = vi.fn();
    const saved = { id: 71, tier: 'long', loot: { coins: 14, items: [] } };
    startExpedition.mockResolvedValue(saved);
    render(<ExpeditionLaunchSheet mount={mount} onDismiss={dismiss} onLaunched={launched} />);
    await userEvent.setup().click(screen.getByRole('button', { name: /Long expedition/ }));
    expect(startExpedition).toHaveBeenCalledExactlyOnceWith(51, 'long');
    expect(launched).toHaveBeenCalledExactlyOnceWith(saved);
    expect(dismiss).toHaveBeenCalledOnce();
  });
});
