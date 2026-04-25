import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardFormModal from './RewardFormModal.jsx';
import { server } from '../../test/server.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('RewardFormModal', () => {
  it('creates a new reward', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.post('*/api/rewards/', () => HttpResponse.json({ id: 1 })),
    );
    render(<RewardFormModal onClose={vi.fn()} onSaved={onSaved} />);
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'Ice Cream');
    await user.type(screen.getAllByRole('spinbutton')[0], '50');
    await user.click(screen.getByRole('button', { name: /^create$/i }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });

  it('edits an existing reward', () => {
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])));
    render(
      <RewardFormModal
        reward={{ id: 3, name: 'Toy', cost_coins: 20, rarity: 'common', is_active: true, requires_parent_approval: true, order: 0 }}
        onClose={vi.fn()}
        onSaved={vi.fn()}
      />,
    );
    expect(screen.getByDisplayValue('Toy')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /update/i })).toBeInTheDocument();
  });

  it('submits digital reward fulfillment fields', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    server.use(
      http.get('*/api/items/catalog/', () =>
        HttpResponse.json([
          { id: 9, name: 'Streak Freeze', icon: '❄️', item_type: 'consumable', type_display: 'Consumable' },
        ]),
      ),
    );
    const calls = [];
    server.use(http.post(/\/api\/rewards\/$/, async ({ request }) => {
      const form = await request.formData();
      calls.push({
        fulfillment_kind: form.get('fulfillment_kind'),
        item_definition: form.get('item_definition'),
      });
      return HttpResponse.json({ id: 2 });
    }));

    render(<RewardFormModal onClose={vi.fn()} onSaved={onSaved} />);
    const inputs = screen.getAllByRole('textbox');
    await user.type(inputs[0], 'Buy Freeze');
    await user.type(screen.getAllByRole('spinbutton')[0], '60');
    await user.selectOptions(screen.getByLabelText(/fulfillment/i), 'digital_item');
    await user.selectOptions(await screen.findByLabelText(/inventory item/i), '9');
    await user.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].fulfillment_kind).toBe('digital_item');
    expect(calls[0].item_definition).toBe('9');
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
  });
});
