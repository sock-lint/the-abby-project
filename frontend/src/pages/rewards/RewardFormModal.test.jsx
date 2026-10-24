import { selectDropdown, openDropdown } from '../../test/selectDropdown';
import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RewardFormModal from './RewardFormModal.jsx';
import { server } from '../../test/server.js';
import { spyHandler } from '../../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

describe('RewardFormModal', () => {
  it.each(['digital_item', 'both'])('warns about an unlimited underpriced pouch for %s and still saves the chosen offer', async (kind) => {
    const user = userEvent.setup();
    const forms = [];
    const create = spyHandler('post', /\/api\/rewards\/$/, ({ request }) => {
      forms.push(request.clone().formData().then((form) => Object.fromEntries(form)));
      return { id: 4 };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([
      { id: 21, name: 'Test pouch', item_type: 'coin_pouch', metadata: { coins: 100 }, coin_value: 200 },
    ])), create.handler);
    render(<RewardFormModal onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.type(screen.getByLabelText('Name'), 'Pouch offer');
    await user.type(screen.getByLabelText('Cost (coins)'), '60');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Fulfillment' }), kind);
    const items = await openDropdown(user, screen.getByRole('combobox', { name: 'Inventory item' }));
    await user.click(await items.findByRole('option', { name: /Test pouch/ }));
    expect(screen.getByRole('status')).toHaveTextContent('This unlimited offer costs 60 Coins and its pouch pays 100 Coins, a net gain of 40 Coins per purchase.');
    expect(screen.getByRole('button', { name: 'Create' })).toBeEnabled();
    expect(create.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(await forms[0]).toMatchObject({ cost_coins: '60', stock: '', item_definition: '21', fulfillment_kind: kind });
  });

  it.each([
    [{}, 100], [{ coins: 0 }, 100], [{ coins: '100' }, 200], [{ coins: 100.9 }, 200],
  ])('uses the pouch opening payout for metadata %j and coin value %s', async (metadata, coinValue) => {
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([
      { id: 21, name: 'Test pouch', item_type: 'coin_pouch', metadata, coin_value: coinValue },
    ])));
    render(<RewardFormModal reward={{ id: 3, name: 'Pouch offer', cost_coins: 60, fulfillment_kind: 'digital_item', item_definition: 21 }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(await screen.findByRole('status')).toHaveTextContent('its pouch pays 100 Coins, a net gain of 40 Coins');
  });

  it('updates the warning as stock, price, selected item and fulfillment change', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([
      { id: 21, name: 'Test pouch', item_type: 'coin_pouch', metadata: { coins: 100 } },
      { id: 22, name: 'Test food', item_type: 'food', coin_value: 200 },
    ])));
    render(<RewardFormModal reward={{ id: 3, name: 'Pouch offer', cost_coins: 60, fulfillment_kind: 'digital_item', item_definition: 21 }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(await screen.findByRole('status')).toHaveTextContent('net gain of 40 Coins');
    const stock = screen.getByLabelText('Stock (blank = unlimited)');
    await user.type(stock, '1');
    expect(screen.queryByRole('status')).toBeNull();
    await user.clear(stock);
    await user.type(stock, '0');
    expect(screen.queryByRole('status')).toBeNull();
    await user.clear(stock);
    expect(screen.getByRole('status')).toBeInTheDocument();
    const cost = screen.getByLabelText('Cost (coins)');
    await user.clear(cost);
    expect(screen.queryByRole('status')).toBeNull();
    await user.type(cost, '100');
    expect(screen.queryByRole('status')).toBeNull();
    await user.clear(cost);
    await user.type(cost, '101');
    expect(screen.queryByRole('status')).toBeNull();
    await user.clear(cost);
    await user.type(cost, '0');
    expect(screen.getByRole('status')).toHaveTextContent('costs 0 Coins');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Inventory item' }), '22');
    expect(screen.queryByRole('status')).toBeNull();
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Inventory item' }), '21');
    expect(screen.getByRole('status')).toBeInTheDocument();
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Fulfillment' }), 'real_world');
    expect(screen.queryByRole('status')).toBeNull();
  });

  it.each([
    [{}, 0], [{ coins: 'unknown' }, 200], [{ coins: '100.5' }, 200], [{ coins: '0' }, 200],
  ])('does not invent a pouch payout from metadata %j and coin value %s', async (metadata, coinValue) => {
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([
      { id: 21, name: 'Test pouch', item_type: 'coin_pouch', metadata, coin_value: coinValue },
    ])));
    render(<RewardFormModal reward={{ id: 3, name: 'Pouch offer', cost_coins: 0, fulfillment_kind: 'digital_item', item_definition: 21 }} onClose={vi.fn()} onSaved={vi.fn()} />);
    await waitFor(() => expect(screen.getByRole('combobox', { name: 'Inventory item' })).toHaveTextContent('Test pouch'));
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('uses the submitted integer price for an exponent-form number input', async () => {
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([
      { id: 21, name: 'Test pouch', item_type: 'coin_pouch', metadata: { coins: 100 } },
    ])));
    render(<RewardFormModal reward={{ id: 3, name: 'Pouch offer', cost_coins: 60, fulfillment_kind: 'digital_item', item_definition: 21 }} onClose={vi.fn()} onSaved={vi.fn()} />);
    await screen.findByRole('status');
    fireEvent.change(screen.getByLabelText('Cost (coins)'), { target: { value: '1e2' } });
    expect(screen.getByRole('status')).toHaveTextContent('costs 1 Coins and its pouch pays 100 Coins, a net gain of 99 Coins');
  });

  it.each([
    ['Small', 3, 150], ['Medium', 10, 500], ['Big', 30, 1500],
  ])('copies the %s active-day suggestion only on click and submits its exact price', async (size, days, coins) => {
    const user = userEvent.setup();
    const forms = [];
    const create = spyHandler('post', /\/api\/rewards\/$/, ({ request }) => {
      forms.push(request.clone().formData().then((form) => Object.fromEntries(form)));
      return { id: 4 };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])), create.handler);
    render(<RewardFormModal onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.type(screen.getByLabelText('Name'), 'Family outing');
    await user.click(screen.getByRole('button', { name: `${size} · ${days} active days · ${coins} Coins` }));
    expect(screen.getByLabelText('Cost (coins)')).toHaveValue(coins);
    expect(create.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(await forms[0]).toMatchObject({ name: 'Family outing', cost_coins: String(coins) });
  });

  it('preserves an existing exact price while editing the planning estimate and submits a custom override', async () => {
    const user = userEvent.setup();
    const forms = [];
    const update = spyHandler('patch', /\/api\/rewards\/3\/$/, ({ request }) => {
      forms.push(request.clone().formData().then((form) => Object.fromEntries(form)));
      return { id: 3 };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])), update.handler);
    render(<RewardFormModal reward={{ id: 3, name: 'Outing', cost_coins: 713 }} onClose={vi.fn()} onSaved={vi.fn()} />);
    const cost = screen.getByLabelText('Cost (coins)');
    const daily = screen.getByLabelText('Estimated Coins per active day');
    expect(cost).toHaveValue(713);
    await user.clear(daily);
    await user.type(daily, '40');
    expect(cost).toHaveValue(713);
    await user.click(screen.getByRole('button', { name: 'Small · 3 active days · 120 Coins' }));
    expect(cost).toHaveValue(120);
    await user.clear(cost);
    await user.type(cost, '137');
    await user.type(screen.getByLabelText('Description'), ' together');
    expect(cost).toHaveValue(137);
    expect(update.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(await forms[0]).toEqual(expect.objectContaining({ cost_coins: '137' }));
    expect(Object.keys(await forms[0])).not.toContain('estimated_coins_per_day');
  });

  it('applies a custom active-day target and leaves exact-price saving available with an invalid guide estimate', async () => {
    const user = userEvent.setup();
    const forms = [];
    const create = spyHandler('post', /\/api\/rewards\/$/, ({ request }) => {
      forms.push(request.clone().formData().then((form) => Object.fromEntries(form)));
      return { id: 4 };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])), create.handler);
    render(<RewardFormModal onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.type(screen.getByLabelText('Name'), 'Trip');
    await user.clear(screen.getByLabelText('Desired active days'));
    await user.type(screen.getByLabelText('Desired active days'), '9');
    await user.click(screen.getByRole('button', { name: 'Use 450 Coins for 9 active days' }));
    expect(screen.getByLabelText('Cost (coins)')).toHaveValue(450);
    await user.clear(screen.getByLabelText('Estimated Coins per active day'));
    await user.type(screen.getByLabelText('Estimated Coins per active day'), '0');
    expect(screen.getByRole('button', { name: /^Small/ })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Use custom price' })).toBeDisabled();
    expect(screen.getByLabelText('Cost (coins)')).toHaveValue(450);
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(await forms[0]).toMatchObject({ cost_coins: '450' });
  });

  it.each([0, 713])('keeps an existing price of %s when only the planning estimate and description change', async (price) => {
    const user = userEvent.setup();
    const forms = [];
    const update = spyHandler('patch', /\/api\/rewards\/3\/$/, ({ request }) => {
      forms.push(request.clone().formData().then((form) => Object.fromEntries(form)));
      return { id: 3 };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])), update.handler);
    render(<RewardFormModal reward={{ id: 3, name: 'Outing', cost_coins: price }} onClose={vi.fn()} onSaved={vi.fn()} />);
    await user.clear(screen.getByLabelText('Estimated Coins per active day'));
    await user.type(screen.getByLabelText('Estimated Coins per active day'), '80');
    await user.type(screen.getByLabelText('Description'), 'Family choice');
    expect(update.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(await forms[0]).toMatchObject({ cost_coins: String(price), description: 'Family choice' });
  });

  it('disables price suggestions and exact-price edits until the saved request finishes', async () => {
    const user = userEvent.setup();
    let release;
    const pending = new Promise((resolve) => { release = resolve; });
    const onSaved = vi.fn();
    const create = spyHandler('post', /\/api\/rewards\/$/, async () => {
      await pending;
      return { id: 4 };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])), create.handler);
    render(<RewardFormModal onClose={vi.fn()} onSaved={onSaved} />);
    await user.type(screen.getByLabelText('Name'), 'Trip');
    await user.click(screen.getByRole('button', { name: 'Small · 3 active days · 150 Coins' }));
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() => expect(create.calls).toHaveLength(1));
    expect(screen.getByLabelText('Cost (coins)')).toBeDisabled();
    expect(screen.getByLabelText('Estimated Coins per active day')).toBeDisabled();
    expect(screen.getByLabelText('Desired active days')).toBeDisabled();
    expect(screen.getByRole('button', { name: /^Medium/ })).toBeDisabled();
    release();
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(screen.getByRole('button', { name: /^Medium/ })).toBeEnabled();
  });

  it.each(['create', 'edit'])('saves a selected icon in the multipart reward %s request only after submit', async (mode) => {
    const user = userEvent.setup();
    const forms = [];
    const write = spyHandler(mode === 'edit' ? 'patch' : 'post', mode === 'edit' ? /\/api\/rewards\/3\/$/ : /\/api\/rewards\/$/, ({ request }) => {
      forms.push(request.clone().formData().then((form) => Object.fromEntries(form)));
      return { id: 3 };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])), write.handler);
    render(<RewardFormModal reward={mode === 'edit' ? { id: 3, name: 'Art time', cost_coins: 20, icon: 'custom' } : undefined} onClose={vi.fn()} onSaved={vi.fn()} />);
    if (mode === 'create') {
      await user.type(screen.getByLabelText('Name'), 'Art time');
      await user.type(screen.getByLabelText('Cost (coins)'), '20');
    } else {
      expect(screen.getByLabelText('Icon (emoji)')).toHaveValue('custom');
    }
    await user.click(screen.getByRole('button', { name: 'Choose icon' }));
    await user.click(screen.getByRole('button', { name: 'Art' }));
    expect(screen.getByLabelText('Icon (emoji)')).toHaveValue('🎨');
    expect(write.calls).toHaveLength(0);
    await user.click(screen.getByRole('button', { name: mode === 'edit' ? 'Update' : 'Create' }));
    await waitFor(() => expect(write.calls).toHaveLength(1));
    expect(await forms[0]).toMatchObject({ name: 'Art time', icon: '🎨', cost_coins: '20', fulfillment_kind: 'real_world' });
  });

  it('preserves a custom reward icon when editing other fields', async () => {
    const user = userEvent.setup();
    const forms = [];
    const update = spyHandler('patch', /\/api\/rewards\/3\/$/, ({ request }) => {
      forms.push(request.clone().formData().then((form) => Object.fromEntries(form)));
      return { id: 3 };
    });
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([])), update.handler);
    render(<RewardFormModal reward={{ id: 3, name: 'Art time', cost_coins: 20, icon: 'family mark' }} onClose={vi.fn()} onSaved={vi.fn()} />);
    expect(screen.getByLabelText('Icon (emoji)')).toHaveValue('family mark');
    await user.type(screen.getByLabelText('Name'), ' together');
    await user.click(screen.getByRole('button', { name: 'Update' }));
    await waitFor(() => expect(update.calls).toHaveLength(1));
    expect(await forms[0]).toMatchObject({ name: 'Art time together', icon: 'family mark' });
  });

  it('does not offer unavailable catalog items for a new digital reward', async () => {
    const user = userEvent.setup();
    server.use(http.get('*/api/items/catalog/', () => HttpResponse.json([
      { id: 1, name: 'Birdseed', item_type: 'food', catalog_available: true },
      { id: 2, name: 'Party Hat', item_type: 'cosmetic_pet_accessory', catalog_available: false },
    ])));
    render(<RewardFormModal onClose={vi.fn()} onSaved={vi.fn()} />);
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Fulfillment' }), 'digital_item');
    const items = await openDropdown(user, await screen.findByLabelText(/inventory item/i));
    expect(await items.findByRole('option', { name: /Birdseed/ })).toBeInTheDocument();
    expect(items.queryByRole('option', { name: /Party Hat/ })).toBeNull();
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
    await selectDropdown(user, screen.getByLabelText(/fulfillment/i), 'digital_item');
    await selectDropdown(user, await screen.findByLabelText(/inventory item/i), '9');
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
