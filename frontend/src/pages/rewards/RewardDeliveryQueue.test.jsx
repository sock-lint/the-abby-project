import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardDeliveryQueue from './RewardDeliveryQueue';

const reward = { id: 4, user_name: 'Abby', reward: { name: 'Book', fulfillment_kind: 'real_world' }, coin_cost_snapshot: 30 };

describe('RewardDeliveryQueue', () => {
  it('can cancel delivery confirmation without changing the reward', async () => {
    const user = userEvent.setup();
    const deliver = vi.fn();
    render(<RewardDeliveryQueue rewards={[reward]} onDeliver={deliver} />);
    await user.click(screen.getByRole('button', { name: 'Mark delivered' }));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(deliver).not.toHaveBeenCalled();
  });

  it('keeps the same delivery available after an uncertain save and permits a safe retry', async () => {
    const user = userEvent.setup();
    const deliver = vi.fn().mockRejectedValueOnce(new Error('The save was not confirmed.')).mockResolvedValue({ status: 'fulfilled' });
    render(<RewardDeliveryQueue rewards={[reward]} onDeliver={deliver} />);
    await user.click(screen.getByRole('button', { name: 'Mark delivered' }));
    await user.click(screen.getByRole('button', { name: 'Confirm delivered' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The save was not confirmed.');
    await user.click(screen.getByRole('button', { name: 'Confirm delivered' }));
    await waitFor(() => expect(deliver).toHaveBeenCalledTimes(2));
    expect(deliver.mock.calls).toEqual([[4], [4]]);
  });
});
