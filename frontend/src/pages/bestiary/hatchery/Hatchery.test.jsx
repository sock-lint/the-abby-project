import { selectDropdown, openDropdown } from '../../../test/selectDropdown';
import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import userEvent from '@testing-library/user-event';
import { render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Hatchery from './Hatchery.jsx';
import { server } from '../../../test/server.js';
import { spyHandler } from '../../../test/spy.js';
import rosterInventory from '../../../../../contracts/api/fixtures/inventory-roster-hatching.json';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

vi.mock('../../../pedestal/PedestalPreview', () => ({
  default: ({ eggAssetId = 'normal-egg' }) => <div role="img" aria-label="Decorative model preview" data-egg={eggAssetId} />,
}));

function renderHatchery() {
  return render(
    <MemoryRouter>
      <Hatchery />
    </MemoryRouter>,
  );
}

describe('Hatchery', () => {
  it('shows the selected egg acquisition rarity and keeps it separate from growth', async () => {
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], total_possible: 15 })),
      http.get('*/api/inventory/', () => HttpResponse.json([
        { quantity: 1, item: { id: 11, name: 'Dragon Spark Egg', item_type: 'egg', rarity: 'legendary', pet_species_slug: 'meshtint-dragon', pet_species_name: 'Dragon Spark' } },
        { quantity: 1, item: { id: 12, name: 'Base Potion', item_type: 'potion', rarity: 'common' } },
      ])),
    );
    const user = userEvent.setup();
    renderHatchery();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), '11');
    expect(screen.getByText('legendary companion · rarity stays the same as it grows')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Dragon Spark family' })).toBeInTheDocument();
  });

  it.each([
    [{ id: 11, slug: 'chick-egg', name: 'Chick Egg', item_type: 'egg', pet_species_slug: 'chick', pet_species_name: 'Chick', metadata: { species: 'chick' } }, ['Chick', 'Fledgling', 'Bird']],
    [rosterInventory.find(({ item }) => item.slug === 'meshtint-bat-egg').item, ['Bat', 'Vampire Bat', 'Bat Lord']],
  ])('names the selected $name family forms for its selected Base potion without hatching', async (egg, forms) => {
    const base = rosterInventory.find(({ item }) => item.slug === 'base-potion');
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [] })),
      http.get('*/api/inventory/', () => HttpResponse.json([{ id: 1, quantity: 1, item: egg }, base])),
    );
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, {});
    server.use(hatch.handler);
    const user = userEvent.setup();
    renderHatchery();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), String(egg.id));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(base.item.id));
    const steps = within(screen.getByRole('list', { name: 'Pet growth stages' })).getAllByRole('listitem');
    expect(steps[0]).toHaveAttribute('aria-current', 'step');
    for (const [index, form] of forms.entries()) {
      expect(steps[index + 1]).toHaveTextContent(`${['Baby', 'Middle', 'Grown'][index]} · ${form}`);
      expect(steps[index + 1]).not.toHaveAttribute('aria-current');
    }
    expect(hatch.calls).toHaveLength(0);
  });

  it('does not borrow family form names for a conflicting egg identity or incompatible potion', async () => {
    const chick = { id: 11, slug: 'chick-egg', name: 'Chick Egg', item_type: 'egg', pet_species_slug: 'chick', pet_species_name: 'Chick', metadata: { species: 'chick' } };
    const conflict = { ...chick, id: 12, name: 'Fledgling Egg', metadata: { species: 'meshtint-bat' } };
    const base = rosterInventory.find(({ item }) => item.slug === 'base-potion');
    const fire = { id: 53, slug: 'fire-potion', name: 'Base Potion', item_type: 'potion', metadata: { variant: 'fire' } };
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [] })),
      http.get('*/api/inventory/', () => HttpResponse.json([
        ...[chick, conflict, fire].map((item) => ({ id: item.id, quantity: 1, item })), base,
      ])),
    );
    const user = userEvent.setup();
    renderHatchery();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), String(conflict.id));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(base.item.id));
    const guide = screen.getByRole('list', { name: 'Pet growth stages' });
    expect(within(guide).queryByText(/Chick|Fledgling|Bird|Vampire Bat|Bat Lord/)).toBeNull();
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Egg' }), String(chick.id));
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), String(fire.id));
    expect(within(guide).queryByText(/Chick|Fledgling|Bird/)).toBeNull();
  });

  it('connects the selected egg to its four-stage family and previews hatching into a baby without consuming anything', async () => {
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [] })),
      http.get('*/api/inventory/', () => HttpResponse.json([
        { id: 1, quantity: 1, item: { id: 11, name: 'Fox Egg', item_type: 'egg', pet_species_slug: 'fox', pet_species_name: 'Fox', lifecycle_stage: 'egg' } },
        { id: 2, quantity: 1, item: { id: 12, name: 'Base Potion', item_type: 'potion' } },
      ])),
    );
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, {});
    server.use(hatch.handler);
    const user = userEvent.setup();
    renderHatchery();
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), '11');
    expect(screen.getByRole('heading', { name: 'Fox family' })).toBeInTheDocument();
    expect(screen.getByText('Hatches into a baby Fox.')).toBeInTheDocument();
    const steps = screen.getByRole('list', { name: 'Pet growth stages' }).querySelectorAll('li');
    expect(steps).toHaveLength(4);
    expect(steps[0]).toHaveAttribute('aria-current', 'step');
    expect(screen.queryByText(/Fledgling|Bird/)).toBeNull();
    expect(hatch.calls).toHaveLength(0);
  });

  it('offers only approved hatch ingredients', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], total_possible: 1 })),
      http.get('*/api/inventory/', () => HttpResponse.json([
        { id: 1, quantity: 1, item: { id: 11, name: 'Chick Egg', item_type: 'egg', catalog_available: true } },
        { id: 2, quantity: 1, item: { id: 12, name: 'Base Potion', item_type: 'potion', catalog_available: true } },
        { id: 3, quantity: 1, item: { id: 13, name: 'Earlier Wolf Egg', item_type: 'egg', catalog_available: false } },
        { id: 4, quantity: 1, item: { id: 14, name: 'Fire Potion', item_type: 'potion', catalog_available: false } },
      ])),
    );
    renderHatchery();
    expect(await screen.findByRole('combobox', { name: 'Egg' })).toBeInTheDocument();
    const eggs = await openDropdown(user, screen.getByRole('combobox', { name: 'Egg' }));
    expect(eggs.getByRole('option', { name: /Chick Egg/ })).toBeInTheDocument();
    expect(eggs.queryByRole('option', { name: /Earlier Wolf Egg/ })).toBeNull();
    const potions = await openDropdown(user, screen.getByRole('combobox', { name: 'Potion' }));
    expect(potions.queryByRole('option', { name: /Fire Potion/ })).toBeNull();
    expect(screen.queryByRole('combobox', { name: /grown pet/ })).toBeNull();
    expect(screen.queryByText(/hybrid/i)).toBeNull();
    expect(screen.getByRole('img', { name: 'Decorative model preview' })).toHaveAttribute('data-egg', 'normal-egg');
  });
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
    expect(screen.queryByRole('img', { name: 'Decorative model preview' })).toBeNull();
  });

  // "No eggs or potions in your Satchel yet…" used to render on a failed
  // satchel fetch too — an empty-inventory message for a broken load.
  it('shows a retry-able error instead of the empty state when the satchel fetch fails', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () =>
        HttpResponse.json({ detail: 'Satchel offline' }, { status: 500 }),
      ),
    );
    renderHatchery();
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toMatch(/satchel offline/i),
    );
    expect(screen.queryByText(/no eggs or potions/i)).toBeNull();
    expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('renders the hatch section with its Meadow chapter marker', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    const { container } = renderHatchery();
    await waitFor(() => expect(screen.getByText('Incubate a new pet')).toBeInTheDocument());
    expect(container.querySelector('[data-chapter-marker="1"]')).toHaveTextContent('1');
    expect(container.querySelector('[data-chapter-marker="2"]')).toBeNull();
  });

  it('starts incubation using the egg + potion picked from the satchel', async () => {
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
    const hatch = spyHandler('post', /\/api\/pets\/incubations\/$/, {
      incubation: { id: 7, egg: { name: 'Dragon Egg' }, potion: { name: 'Fire Potion' }, remaining_seconds: 7200, is_ready: false, status: 'incubating' },
      server_now: '2026-10-18T10:00:00Z',
    });
    server.use(hatch.handler);

    renderHatchery();
    const user = userEvent.setup();

    await selectDropdown(user, await screen.findByRole('combobox', { name: /^egg$/i }), '11');
    await selectDropdown(user, screen.getByRole('combobox', { name: /^potion$/i }), '22');
    await user.click(screen.getByRole('button', { name: /start incubation/i }));

    await waitFor(() => expect(hatch.calls).toHaveLength(1));
    expect(hatch.calls[0].body).toEqual({ egg_item_id: '11', potion_item_id: '22', request_id: expect.any(String) });
    expect(hatch.calls[0].url).toMatch(/\/api\/pets\/incubations\/$/);
  });

  it('keeps artwork neutral and preserves the hatch form without a ceremony after a rejected hatch', async () => {
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [] })),
      http.get('*/api/inventory/', () => HttpResponse.json([
        { id: 1, quantity: 1, item: { id: 11, name: 'A very long saved egg name including Legendary artwork words', item_type: 'egg', catalog_available: true } },
        { id: 2, quantity: 1, item: { id: 22, name: 'Base Potion', item_type: 'potion', catalog_available: true } },
      ])),
    );
    const hatch = spyHandler('post', /\/api\/pets\/incubations\/$/, HttpResponse.json({ detail: 'This pair cannot be hatched.' }, { status: 400 }));
    server.use(hatch.handler);
    renderHatchery();
    const user = userEvent.setup();
    const egg = await screen.findByRole('combobox', { name: /^egg$/i });
    const potion = screen.getByRole('combobox', { name: /^potion$/i });
    await selectDropdown(user, egg, '11');
    await selectDropdown(user, potion, '22');
    expect(hatch.calls).toHaveLength(0);
    expect(screen.getByRole('img', { name: 'Decorative model preview' })).toHaveAttribute('data-egg', 'normal-egg');
    expect(screen.queryByRole('alertdialog')).toBeNull();
    await user.click(screen.getByRole('button', { name: /start incubation/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This pair cannot be hatched.');
    expect(hatch.calls).toHaveLength(1);
    expect(hatch.calls[0].url).toMatch(/\/api\/pets\/incubations\/$/);
    expect(hatch.calls[0].body).toEqual({ egg_item_id: '11', potion_item_id: '22', request_id: expect.any(String) });
    expect(egg).toHaveTextContent('A very long saved egg name including Legendary artwork words');
    expect(potion).toHaveTextContent('Base Potion');
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByText(/You hatched a/)).toBeNull();
  });

});
