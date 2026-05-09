import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Hatchery from './Hatchery.jsx';
import { server } from '../../../test/server.js';
import { spyHandler } from '../../../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

function renderHatchery() {
  return render(
    <MemoryRouter>
      <Hatchery />
    </MemoryRouter>,
  );
}

describe('Hatchery', () => {
  it('renders an empty state when there are no eggs or potions', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    renderHatchery();
    await waitFor(() =>
      expect(screen.getByText(/no eggs or potions/i)).toBeInTheDocument(),
    );
  });

  it('hatches a pet using the egg + potion picked from the satchel', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () =>
        HttpResponse.json([
          { id: 1, quantity: 1, item: { id: 11, name: 'Dragon Egg', icon: '🥚', item_type: 'egg' } },
          { id: 2, quantity: 1, item: { id: 22, name: 'Fire Potion', icon: '🧪', item_type: 'potion' } },
        ]),
      ),
    );
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, {
      species: { name: 'Dragon' },
      potion: { name: 'Fire' },
    });
    server.use(hatch.handler);

    renderHatchery();
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByRole('combobox', { name: /^egg$/i }), '11');
    await user.selectOptions(screen.getByRole('combobox', { name: /^potion$/i }), '22');
    await user.click(screen.getByRole('button', { name: /perform the ritual/i }));

    await waitFor(() => expect(hatch.calls).toHaveLength(1));
    expect(hatch.calls[0].body).toEqual({ egg_item_id: '11', potion_item_id: '22' });
    expect(hatch.calls[0].url).toMatch(/\/api\/pets\/hatch\/$/);
  });

  it('disables resting mounts in the breed picker and breeds two ready mounts', async () => {
    const justBred = new Date().toISOString();
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({
          pets: [],
          mounts: [
            { id: 9, species: { icon: '🐺', name: 'Wolf' }, potion: { name: 'Base' }, is_active: false, last_bred_at: null },
            { id: 10, species: { icon: '🦊', name: 'Fox' }, potion: { name: 'Fire' }, is_active: false, last_bred_at: null },
            { id: 11, species: { icon: '🦁', name: 'Lion' }, potion: { name: 'Ice' }, is_active: false, last_bred_at: justBred },
          ],
          total_possible: 48,
        }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    const breed = spyHandler('post', /\/api\/mounts\/breed\/$/, {
      egg_item_name: 'Wolf-Fire Egg',
      potion_item_name: 'Fire Potion',
      cooldown_days: 7,
      chromatic: false,
    });
    server.use(breed.handler);

    renderHatchery();
    const user = userEvent.setup();

    const firstPicker = await screen.findByRole('combobox', { name: /first mount/i });
    const restingOption = Array.from(firstPicker.options).find((o) => /lion/i.test(o.textContent || ''));
    expect(restingOption?.disabled).toBe(true);
    expect(restingOption?.textContent).toMatch(/resting \d+d/);

    await user.selectOptions(firstPicker, '9');
    await user.selectOptions(screen.getByRole('combobox', { name: /second mount/i }), '10');
    await user.click(screen.getByRole('button', { name: /breed the pair/i }));

    await waitFor(() => expect(breed.calls).toHaveLength(1));
    expect(breed.calls[0].body).toEqual({ mount_a_id: '9', mount_b_id: '10' });
    expect(breed.calls[0].url).toMatch(/\/api\/mounts\/breed\/$/);
  });

  it('mounts the PetCeremonyModal in breed mode with the selected parents after a successful breed', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({
          pets: [],
          mounts: [
            { id: 9, species: { icon: '🐺', name: 'Wolf', sprite_key: 'wolf' }, potion: { name: 'Base', slug: 'base' }, is_active: false, last_bred_at: null },
            { id: 10, species: { icon: '🦊', name: 'Fox', sprite_key: 'fox' }, potion: { name: 'Fire', slug: 'fire' }, is_active: false, last_bred_at: null },
          ],
          total_possible: 48,
        }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      http.post('*/api/mounts/breed/', () =>
        HttpResponse.json({
          egg_item_id: 99,
          egg_item_name: 'Wolf Egg',
          egg_item_icon: '🥚',
          egg_item_sprite_key: 'big-egg',
          potion_item_id: 100,
          potion_item_name: 'Fire Potion',
          potion_item_icon: '🧪',
          potion_item_sprite_key: '',
          picked_species: 'Wolf',
          picked_species_slug: 'wolf',
          picked_potion: 'Fire',
          picked_potion_slug: 'fire',
          chromatic: false,
          cooldown_days: 7,
        }),
      ),
    );

    renderHatchery();
    const user = userEvent.setup();

    await user.selectOptions(await screen.findByRole('combobox', { name: /first mount/i }), '9');
    await user.selectOptions(screen.getByRole('combobox', { name: /second mount/i }), '10');
    await user.click(screen.getByRole('button', { name: /breed the pair/i }));

    // The celebration modal mounts and renders the result egg headline +
    // the "hybrid is conceived" kicker (non-chromatic path).
    await waitFor(() => {
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });
    expect(screen.getByText(/wolf egg/i)).toBeInTheDocument();
    expect(screen.getByText(/a hybrid is conceived/i)).toBeInTheDocument();
  });
});
