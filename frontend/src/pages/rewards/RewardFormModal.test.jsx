import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardFormModal from './RewardFormModal.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('RewardFormModal', () => {
  it('does not offer unavailable catalog items for a new digital reward', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([
      { id: 1, name: 'Birdseed', item_type: 'food', catalog_available: true },
      { id: 2, name: 'Party Hat', item_type: 'cosmetic_pet_accessory', catalog_available: false },
    ])));
    render(<RewardFormModal onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.selectOptions(screen.getByRole('combobox', { name: 'Fulfillment' }), 'digital_item');
    expect(await screen.findByRole('option', { name: /Birdseed/ })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /Party Hat/ })).toBeNull();
  });
  it.each([0, 7])('clears existing stock %s to unlimited with an explicit empty multipart field', async (stock) => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const forms = [];
    const update = spyHandler('patch', /\/api\/rewards\/3\/$/, ({ request }) => {
      forms.push(request.clone().formData().then((form) => Object.fromEntries(form)));
      return { id: 3, stock: null };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])), update.handler);
    render(<RewardFormModal reward={{ id: 3, name: 'Toy', cost_coins: 20, stock }} onClose={vi.fn()} onSaved={onSaved} />);

    await user.clear(screen.getByLabelText(/stock/i));
    await user.click(screen.getByRole('button', { name: /update/i }));

    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(update.calls[0].url).toMatch(/\/api\/rewards\/3\/$/);
    expect(await forms[0]).toEqual({
      name: 'Toy', description: '', icon: '', cost_coins: '20', rarity: 'common',
      stock: '', requires_parent_approval: 'true', is_active: 'true', order: '0',
      fulfillment_kind: 'real_world', item_definition: '',
    });
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  });

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

  it('wires both toggles as labelled checkboxes', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])));
    render(<RewardFormModal onClose={vi.fn()} onSaved={vi.fn()} />);

    const approval = screen.getByLabelText(/requires approval/i);
    const active = screen.getByLabelText(/^active$/i);
    expect(approval).toBeChecked();
    expect(active).toBeChecked();

    await user.click(approval);
    expect(approval).not.toBeChecked();
    expect(active).toBeChecked();
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

  it('labels the image picker and submits the chosen file', async () => {
    const user = userEvent.setup();
    const onSaved = vi.fn();
    const uploads = [];
    server.use(
      http.get('*/api/items/catalog/', () => HttpResponse.json([])),
      http.post(/\/api\/rewards\/$/, async ({ request }) => {
        const form = await request.formData();
        const image = form.get('image');
        uploads.push(image?.type);
        return HttpResponse.json({ id: 4 });
      }),
    );
    render(<RewardFormModal onClose={vi.fn()} onSaved={onSaved} />);

    const picker = screen.getByLabelText('Image');
    expect(picker).toHaveAttribute('type', 'file');
    await user.type(screen.getByLabelText('Name'), 'Sticker');
    await user.type(screen.getAllByRole('spinbutton')[0], '5');
    await user.upload(picker, new File(['png'], 'sticker.png', { type: 'image/png' }));
    await user.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(uploads).toEqual(['image/png']);
  });
});
