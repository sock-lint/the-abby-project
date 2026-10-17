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
  it.each([
    [{ id: 11, slug: 'chick-egg', name: 'Chick Egg', item_type: 'egg', pet_species_slug: 'chick', pet_species_name: 'Chick', metadata: { species: 'chick' } }, ['Chick', 'Fledgling', 'Bird']],
    [rosterInventory.find(({ item }) => item.slug === 'meshtint-bat-egg').item, ['Bat', 'Vampire Bat', 'Bat Lord']],
  ])('names the selected $name family forms for its selected Base potion without hatching', async (egg, forms) => {
    const base = rosterInventory.find(({ item }) => item.slug === 'base-potion');
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], breeding_available: false })),
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
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], breeding_available: false })),
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
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], breeding_available: false })),
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

  it('offers only approved ingredients and explains unavailable breeding without suggesting a hybrid', async () => {
    const user = userEvent.setup();
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [{ id: 1, can_breed: false }, { id: 2, can_breed: false }], total_possible: 1, breeding_available: false })),
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
    expect(screen.getByText(/Breeding is not available with the current pet collection/)).toBeInTheDocument();
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

  it('renders the Hatch + Breed sections with Meadow chapter markers', async () => {
    server.use(
      http.get('*/api/pets/stable/', () =>
        HttpResponse.json({ pets: [], mounts: [], total_possible: 48 }),
      ),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
    );
    const { container } = renderHatchery();
    await waitFor(() => expect(screen.getByText('Hatch a new pet')).toBeInTheDocument());
    expect(container.querySelector('[data-chapter-marker="1"]')).toHaveTextContent('1');
    expect(container.querySelector('[data-chapter-marker="2"]')).toHaveTextContent('2');
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

    await selectDropdown(user, await screen.findByRole('combobox', { name: /^egg$/i }), '11');
    await selectDropdown(user, screen.getByRole('combobox', { name: /^potion$/i }), '22');
    await user.click(screen.getByRole('button', { name: /hatch pet/i }));

    await waitFor(() => expect(hatch.calls).toHaveLength(1));
    expect(hatch.calls[0].body).toEqual({ egg_item_id: '11', potion_item_id: '22' });
    expect(hatch.calls[0].url).toMatch(/\/api\/pets\/hatch\/$/);
  });

  it('keeps artwork neutral and preserves the hatch form without a ceremony after a rejected hatch', async () => {
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], breeding_available: false })),
      http.get('*/api/inventory/', () => HttpResponse.json([
        { id: 1, quantity: 1, item: { id: 11, name: 'A very long saved egg name including Legendary artwork words', item_type: 'egg', catalog_available: true } },
        { id: 2, quantity: 1, item: { id: 22, name: 'Base Potion', item_type: 'potion', catalog_available: true } },
      ])),
    );
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, HttpResponse.json({ detail: 'This pair cannot be hatched.' }, { status: 400 }));
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
    await user.click(screen.getByRole('button', { name: /hatch pet/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent('This pair cannot be hatched.');
    expect(hatch.calls).toHaveLength(1);
    expect(hatch.calls[0].url).toMatch(/\/api\/pets\/hatch\/$/);
    expect(hatch.calls[0].body).toEqual({ egg_item_id: '11', potion_item_id: '22' });
    expect(egg).toHaveTextContent('A very long saved egg name including Legendary artwork words');
    expect(potion).toHaveTextContent('Base Potion');
    expect(screen.queryByRole('alertdialog')).toBeNull();
    expect(screen.queryByText(/You hatched a/)).toBeNull();
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

    const firstPicker = await screen.findByRole('combobox', { name: /first grown pet/i });
    const grownPets = await openDropdown(user, firstPicker);
    const restingOption = grownPets.getByRole('option', { name: /lion/i });
    expect(restingOption).toHaveAttribute('aria-disabled', 'true');
    expect(restingOption?.textContent).toMatch(/resting \d+d/);

    await selectDropdown(user, firstPicker, '9');
    await selectDropdown(user, screen.getByRole('combobox', { name: /second grown pet/i }), '10');
    await user.click(screen.getByRole('button', { name: /breed pets/i }));

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

    await selectDropdown(user, await screen.findByRole('combobox', { name: /first grown pet/i }), '9');
    await selectDropdown(user, screen.getByRole('combobox', { name: /second grown pet/i }), '10');
    await user.click(screen.getByRole('button', { name: /breed pets/i }));

    // The celebration modal mounts and renders the result egg headline +
    // the "hybrid is conceived" kicker (non-chromatic path).
    await waitFor(() => {
      expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    });
    expect(screen.getByText(/wolf egg/i)).toBeInTheDocument();
    expect(screen.getByText(/a new egg/i)).toBeInTheDocument();
  });
});
