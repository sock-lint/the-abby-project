import { describe, expect, it, vi } from 'vitest';
import { http, HttpResponse } from 'msw';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import BestiaryHub from './index.jsx';
import { AuthProvider } from '../../hooks/useApi.js';
import { server } from '../../test/server.js';
import { buildUser } from '../../test/factories.js';
import { selectDropdown } from '../../test/selectDropdown.js';
import { spyHandler } from '../../test/spy.js';

vi.mock('framer-motion', async () => {
  const a = await vi.importActual('framer-motion');
  return { ...a, AnimatePresence: ({ children }) => children };
});

vi.mock('../../components/companion/CompanionPreview', () => ({
  default: ({ children }) => <section aria-label="Companion home">{children}</section>,
}));
vi.mock('../../pedestal/PedestalPreview', () => ({ default: () => null }));
vi.mock('./PetCeremonyModal', () => ({
  default: ({ onDismiss }) => <div role="dialog"><button onClick={onDismiss}>Close pet celebration</button></div>,
}));

describe('BestiaryHub', () => {
  function stubAll() {
    server.use(
      http.get('*/api/auth/me/', () => HttpResponse.json(buildUser())),
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [], mounts: [], total_possible: 0 })),
      http.get('*/api/inventory/', () => HttpResponse.json([])),
      http.get('*/api/pets/codex/', () =>
        HttpResponse.json({ species: [], potions: [], totals: { species: 0, discovered_species: 0, mounts_possible: 0, mounts_owned: 0 } }),
      ),
    );
  }

  it('renders the bestiary hub', async () => {
    stubAll();
    render(
      <MemoryRouter>
        <AuthProvider>
          <BestiaryHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    // Hub no longer renders an h1; check the tablist aria-label instead.
    await waitFor(() =>
      expect(screen.getByRole('tablist', { name: /pets sections/i })).toBeInTheDocument(),
    );
  });

  it('exposes Companions, Grown pets, Collection, and Hatchery tabs', async () => {
    stubAll();
    render(
      <MemoryRouter>
        <AuthProvider>
          <BestiaryHub />
        </AuthProvider>
      </MemoryRouter>,
    );
    await screen.findByRole('tab', { name: 'Companions' });
    expect(screen.getByRole('tab', { name: 'Grown pets' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Collection' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Hatchery' })).toBeInTheDocument();
    expect(screen.queryByRole('tab', { name: 'Party' })).toBeNull();
    expect(screen.queryByRole('tab', { name: 'Satchel' })).toBeNull();
  });

  it('shows a newly hatched pet when returning to already visited Companions and Collection tabs', async () => {
    const user = userEvent.setup();
    const species = { id: 42, slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: '🐥', rarity: 'common', catalog_available: true };
    const potion = { id: 41, slug: 'base', name: 'Base', rarity: 'common', catalog_available: true };
    const pet = { id: 1, species, potion, name: 'Peep', lifecycle_stage: 'baby', evolution_stage: 'chick', growth_points: 0, evolved_to_mount: false, is_active: true, catalog_available: true };
    let hatched = false;
    const hatch = spyHandler('post', /\/api\/pets\/hatch\/$/, () => { hatched = true; return HttpResponse.json(pet, { status: 201 }); });
    stubAll();
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: hatched ? [pet] : [], mounts: [], total_possible: 1, breeding_available: false })),
      http.get('*/api/inventory/', () => HttpResponse.json([
        { id: 1, quantity: hatched ? 0 : 1, item: { id: 11, slug: 'chick-egg', name: 'Chick Egg', icon: '🥚', item_type: 'egg', pet_species_slug: 'chick', pet_species_name: 'Chick', metadata: { species: 'chick' }, catalog_available: true } },
        { id: 2, quantity: 1, item: { id: 22, slug: 'base-potion', name: 'Base Potion', item_type: 'potion', metadata: { variant: 'base' }, catalog_available: true } },
      ])),
      http.get('*/api/pets/codex/', () => HttpResponse.json({
        species: [{ ...species, discovered: hatched, owned_pet_ids: hatched ? [1] : [], owned_mount_potion_ids: [], available_potions: [potion] }],
        potions: [potion], totals: { species: 1, discovered_species: hatched ? 1 : 0, mounts_possible: 1, mounts_owned: 0 },
      })),
      hatch.handler,
    );
    render(<MemoryRouter><AuthProvider><BestiaryHub /></AuthProvider></MemoryRouter>);
    expect(await screen.findByText(/No companions yet/)).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Collection' }));
    const collectionSummary = (await screen.findByRole('heading', { name: 'Collection' })).parentElement;
    expect(within(collectionSummary).getByText('0 of 1')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: /^Hatch(?:ing|ery)$/ }));
    await selectDropdown(user, await screen.findByRole('combobox', { name: 'Egg' }), '11');
    await selectDropdown(user, screen.getByRole('combobox', { name: 'Potion' }), '22');
    await user.click(screen.getByRole('tab', { name: 'Companions' }));
    await user.click(screen.getByRole('tab', { name: /^Hatch(?:ing|ery)$/ }));
    expect(screen.getByRole('combobox', { name: 'Egg' })).toHaveTextContent('Chick Egg');
    expect(screen.getByRole('combobox', { name: 'Potion' })).toHaveTextContent('Base Potion');
    await user.click(screen.getByRole('button', { name: 'Hatch pet' }));
    await user.click(await screen.findByRole('button', { name: 'Close pet celebration' }));
    expect(hatch.calls).toHaveLength(1);
    expect(hatch.calls[0]).toMatchObject({ method: 'POST', body: { egg_item_id: '11', potion_item_id: '22' } });
    expect(new URL(hatch.calls[0].url).pathname).toBe('/api/pets/hatch/');
    await user.click(screen.getByRole('tab', { name: 'Companions' }));
    expect(within(await screen.findByRole('list', { name: 'Your companions' })).getByRole('button', { name: 'Care for Base Chick' })).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Collection' }));
    expect(await within(collectionSummary).findByText('1 of 1')).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /^Hatched/ })).toHaveAttribute('aria-selected', 'true');
  });

  it('keeps the middle stage and refreshes previously visited grown pets and collection after feeding to 100', async () => {
    const user = userEvent.setup();
    const species = { id: 42, slug: 'chick', name: 'Chick', sprite_key: 'cute-chick', icon: '🐥', rarity: 'common', catalog_available: true };
    const potion = { id: 41, slug: 'base', name: 'Base', rarity: 'common', catalog_available: true };
    let growth = 49;
    const currentPet = () => ({ id: 1, species, potion, name: 'Peep', lifecycle_stage: growth < 50 ? 'baby' : growth < 100 ? 'middle' : 'grown', evolution_stage: growth < 50 ? 'chick' : growth < 100 ? 'fledgling' : 'bird', growth_points: growth, evolved_to_mount: growth === 100, is_active: true, catalog_available: true });
    const mount = { id: 5, species, potion, catalog_available: true, lifecycle_stage: 'grown', expedition_available: true, can_breed: false };
    const feed = spyHandler('post', /\/api\/pets\/1\/feed\/$/, () => {
      growth = growth === 49 ? 50 : 100;
      return { new_growth: growth, growth_added: growth === 50 ? 1 : 50, evolved: growth === 100, lifecycle_stage: currentPet().lifecycle_stage, evolution_stage: currentPet().evolution_stage };
    });
    stubAll();
    server.use(
      http.get('*/api/pets/stable/', () => HttpResponse.json({ pets: [currentPet()], mounts: growth === 100 ? [mount] : [], total_possible: 1 })),
      http.get('*/api/inventory/', () => HttpResponse.json([{ id: 1, quantity: 2, item: { id: 100, name: 'Birdseed', item_type: 'food' } }])),
      http.get('*/api/pets/codex/', () => HttpResponse.json({
        species: [{ ...species, discovered: true, owned_pet_ids: [1], owned_mount_potion_ids: growth === 100 ? [41] : [], available_potions: [potion] }],
        potions: [potion], totals: { species: 1, discovered_species: 1, mounts_possible: 1, mounts_owned: growth === 100 ? 1 : 0 },
      })),
      feed.handler,
    );
    render(<MemoryRouter><AuthProvider><BestiaryHub /></AuthProvider></MemoryRouter>);
    await screen.findByRole('list', { name: 'Your companions' });
    await user.click(screen.getByRole('tab', { name: 'Grown pets' }));
    expect(await screen.findByText(/No grown pets yet/)).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Collection' }));
    expect(await screen.findByRole('tab', { name: /^Hatched/ })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('tab', { name: 'Companions' }));
    await user.click(screen.getByRole('tab', { name: 'Active (1)' }));
    await user.click(screen.getByRole('button', { name: 'Feed your companion' }));
    await user.click(within(screen.getByRole('dialog', { name: 'Care for Peep' })).getByRole('button', { name: /Birdseed/ }));
    const companions = screen.getByRole('list', { name: 'Your companions' });
    expect(await within(companions).findByRole('button', { name: 'Care for Base Fledgling' })).toHaveTextContent('Middle');
    expect(screen.getByRole('tab', { name: 'Active (1)' })).toHaveAttribute('aria-selected', 'true');
    await user.click(screen.getByRole('button', { name: 'Feed your companion' }));
    await user.click(within(screen.getByRole('dialog', { name: 'Care for Peep' })).getByRole('button', { name: /Birdseed/ }));
    await user.click(await screen.findByRole('button', { name: 'Close pet celebration' }));
    await user.click(screen.getByRole('tab', { name: 'Grown pets' }));
    expect(within(await screen.findByRole('list', { name: 'Your grown pets' })).getByRole('button', { name: 'Visit Base Bird' })).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Collection' }));
    expect(await screen.findByRole('tab', { name: /^Complete,/ })).toHaveAttribute('aria-selected', 'true');
    expect(feed.calls).toHaveLength(2);
    expect(feed.calls.map(({ body }) => body)).toEqual([{ food_item_id: 100 }, { food_item_id: 100 }]);
    expect(feed.calls.every(({ method, url }) => method === 'POST' && new URL(url).pathname === '/api/pets/1/feed/')).toBe(true);
  });
});
